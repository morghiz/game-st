class MybrPlayer extends EventTarget {
    constructor() {
        super();
        this.audioContext = null;
        this._mainGainNode = null;
        this.tracks = [];
        this.trackGainNodes = {};
        this._loopEnabled = false;
        this.loopStartSample = 0;
        this.loopEndSample = 0;
        this._volume = 1;
        this._playbackStartTime = 0;
        this._pausedTime = 0;
        this._isPlaying = false;
        this._src = '';
        this._loadingPromise = null;
        this.onStatusChange = () => {};
        this._endedTrackCount = 0;
    }

    set volume(value) {
        this._volume = Math.max(0, Math.min(1, value));
        if (this._mainGainNode) this._mainGainNode.gain.value = this._volume;
    }

    get volume() {
        return this._volume;
    }

    set loop(value) {
        this._loopEnabled = !!value;
        this.tracks.forEach(track => {
            if (track.sourceNode && track.audioBuffer) {
                track.sourceNode.loop = this._loopEnabled;
                if (this._loopEnabled && this.loopEndSample > this.loopStartSample) {
                    track.sourceNode.loopStart = this.loopStartSample / track.audioBuffer.sampleRate;
                    track.sourceNode.loopEnd = this.loopEndSample / track.audioBuffer.sampleRate;
                } else {
                    track.sourceNode.loopStart = 0;
                    track.sourceNode.loopEnd = track.audioBuffer.duration;
                }
            }
        });
        this.onStatusChange(this._isPlaying ? 'In riproduzione' : (this._pausedTime > 0 ? 'In pausa' : 'Fermo'), this._loopEnabled);
    }

    get loop() {
        return this._loopEnabled;
    }

    get duration() {
        return this.tracks.length > 0 && this.tracks[0].audioBuffer ? this.tracks[0].audioBuffer.duration : 0;
    }

    get currentTime() {
        if (!this.audioContext) return 0;
        if (this._isPlaying) {
            return this._pausedTime + (this.audioContext.currentTime - this._playbackStartTime);
        }
        return this._pausedTime;
    }

    set src(url) {
        if (this._src === url) return;
        this._src = url;
        this.stop();
        this.dispatchEvent(new Event('loadstart'));
        this._loadingPromise = this._fetchAndParseAudio(url);
        this._loadingPromise.then(() => {
            this.dispatchEvent(new Event('canplaythrough'));
        }).catch(e => {
            this.dispatchEvent(new Event('error'));
            console.error('Errore durante il caricamento o la decodifica:', e);
        });
    }

    get src() {
        return this._src;
    }
    
    async _fetchAndParseAudio(url) {
        this.onStatusChange('Caricamento...', this._loopEnabled);
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const contentLength = +response.headers.get('Content-Length');
            let receivedLength = 0;
            const chunks = [];
            
            const reader = response.body.getReader();

            while(true) {
                const { done, value } = await reader.read();
                if (done) break;
                chunks.push(value);
                receivedLength += value.length;
                if (contentLength) {
                    const progress = (receivedLength / contentLength) * 100;
                    this.dispatchEvent(new CustomEvent('loadprogress', { detail: { progress } }));
                }
            }

            let chunksAll = new Uint8Array(receivedLength);
            let position = 0;
            for(let chunk of chunks) {
                chunksAll.set(chunk, position);
                position += chunk.length;
            }
            
            const arrayBuffer = chunksAll.buffer;

            const dataView = new DataView(arrayBuffer);
            let offset = 0;

            const magicNumber = dataView.getUint32(offset, true); offset += 4;
            const numTracks = dataView.getUint8(offset); offset += 1;
            this._loopEnabled = dataView.getUint8(offset) === 1; offset += 1;
            this.loopStartSample = dataView.getUint32(offset, true); offset += 4;
            this.loopEndSample = dataView.getUint32(offset, true); offset += 4;

            const EXPECTED_MAGIC_NUMBER = 0x5242594D;
            if (magicNumber !== EXPECTED_MAGIC_NUMBER) {
                this.onStatusChange(`Errore: Numero Magico non valido. Trovato: 0x${magicNumber.toString(16)}. Atteso: 0x${EXPECTED_MAGIC_NUMBER.toString(16)}.`, this._loopEnabled);
                throw new Error('Numero Magico non valido');
            }

            if (!this.audioContext) this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.tracks = [];
            this.trackGainNodes = {};

            const trackHeaders = [];

            for (let i = 0; i < numTracks; i++) {
                const channels = dataView.getUint8(offset); offset += 1;
                const sampleRate = dataView.getUint32(offset, true); offset += 4;
                const numSamples = dataView.getUint32(offset, true); offset += 4;

                const nameLength = dataView.getUint8(offset); offset += 1;
                const nameBytes = new Uint8Array(arrayBuffer, offset, nameLength);
                const trackName = new TextDecoder().decode(nameBytes);
                offset += nameLength;

                const offsetToData = dataView.getUint32(offset, true); offset += 4;

                trackHeaders.push({ channels, sampleRate, numSamples, trackName, offsetToData });
            }

            const decodePromises = trackHeaders.map(async (header, index) => {
                const wavBuffer = arrayBuffer.slice(header.offsetToData);
                if (wavBuffer.byteLength === 0) return null;
                try {
                    const audioBuffer = await this.audioContext.decodeAudioData(wavBuffer);
                    const gainNode = this.audioContext.createGain();
                    return { audioBuffer, currentVolume: 1.0, name: header.trackName || `Traccia ${index + 1}`, path: url + `#track${index}`, gainNode };
                } catch (e) {
                    console.error(`Errore durante la decodifica della traccia ${index}:`, e);
                    return null;
                }
            });

            const decodedTracks = await Promise.all(decodePromises);
            this.tracks = decodedTracks.filter(track => track !== null);

            if (this.tracks.length === 0) throw new Error("Nessuna traccia audio valida è stata caricata.");

            this.tracks.forEach(track => { this.trackGainNodes[track.name] = track.gainNode; });
            this.onStatusChange('Pronto', this._loopEnabled);
            return { loopEnabled: this._loopEnabled, loopStartSample: this.loopStartSample, loopEndSample: this.loopEndSample };
        } catch (e) {
            this.tracks = [];
            this.trackGainNodes = {};
            this.onStatusChange(`Errore durante il caricamento/decodifica: ${e.message}`, this._loopEnabled);
            throw e;
        }
    }

    async play() {
        if (this.tracks.length === 0 && this._loadingPromise) {
            try {
                await this._loadingPromise;
            } catch (e) {
                return Promise.reject(new Error('Impossibile riprodurre: Errore nel caricamento del file.'));
            }
        }
        if (this.tracks.length === 0 || this._isPlaying) return Promise.resolve();

        if (!this.audioContext) this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        if (this.audioContext.state === 'suspended') {
            try {
                await this.audioContext.resume();
            } catch (e) {
                return Promise.reject(new Error('Errore durante la riattivazione dell\'AudioContext.'));
            }
        }
        this._startPlayback();
        this.onStatusChange('In riproduzione', this._loopEnabled);
        this.dispatchEvent(new Event('play'));
        return Promise.resolve();
    }

    pause() {
        if (!this._isPlaying) return;
        
        const elapsed = this.audioContext.currentTime - this._playbackStartTime;
        this._pausedTime += elapsed;

        this.tracks.forEach(track => {
            if (track.sourceNode) {
                track.sourceNode.onended = null;
                track.sourceNode.stop();
                track.sourceNode.disconnect();
                track.sourceNode = null;
            }
        });
        this._isPlaying = false;
        this._endedTrackCount = 0;
        this.onStatusChange('In pausa', this._loopEnabled);
        this.dispatchEvent(new Event('pause'));
    }

    stop() {
        const wasPlaying = this._isPlaying;
        this.tracks.forEach(track => {
            if (track.sourceNode) {
                track.sourceNode.onended = null;
                track.sourceNode.stop();
                track.sourceNode.disconnect();
                track.sourceNode = null;
            }
        });
        this._isPlaying = false;
        this._pausedTime = 0;
        this._playbackStartTime = 0;
        this._endedTrackCount = 0;
        this.onStatusChange('Fermo', this._loopEnabled);
        if (wasPlaying) this.dispatchEvent(new Event('ended'));
    }

    _startPlayback() {
        if (!this._mainGainNode) {
            this._mainGainNode = this.audioContext.createGain();
            this._mainGainNode.gain.value = this._volume;
            this._mainGainNode.connect(this.audioContext.destination);
        }

        this._playbackStartTime = this.audioContext.currentTime;
        this._endedTrackCount = 0;

        const startOffset = this._pausedTime;
        let effectiveStartOffset = startOffset;
        
        if (this._loopEnabled && this.tracks.length > 0 && this.loopEndSample > this.loopStartSample) {
            const sampleRate = this.tracks[0].audioBuffer.sampleRate;
            const loopStartSec = this.loopStartSample / sampleRate;
            const loopEndSec = this.loopEndSample / sampleRate;
            const loopDuration = loopEndSec - loopStartSec;

            if (startOffset >= loopStartSec && loopDuration > 0) {
                effectiveStartOffset = loopStartSec + ((startOffset - loopStartSec) % loopDuration);
            }
        }

        this.tracks.forEach((track) => {
            if (track.sourceNode) {
                track.sourceNode.stop();
                track.sourceNode.disconnect();
            }
            track.sourceNode = this.audioContext.createBufferSource();
            track.sourceNode.buffer = track.audioBuffer;
            track.sourceNode.loop = this._loopEnabled;

            if (this._loopEnabled && this.loopEndSample > this.loopStartSample) {
                track.sourceNode.loopStart = this.loopStartSample / track.audioBuffer.sampleRate;
                track.sourceNode.loopEnd = this.loopEndSample / track.audioBuffer.sampleRate;
            }

            if (!track.gainNode) {
                track.gainNode = this.audioContext.createGain();
                this.trackGainNodes[track.name] = track.gainNode;
            }

            track.gainNode.connect(this._mainGainNode);
            track.sourceNode.connect(track.gainNode);
            track.sourceNode.start(0, effectiveStartOffset);

            track.sourceNode.onended = () => {
                if (!this._loopEnabled && this._isPlaying) {
                    this._endedTrackCount++;
                    if (this._endedTrackCount >= this.tracks.length) {
                        this.stop();
                    }
                }
            };
        });

        this._isPlaying = true;
    }
    
    setAllTracksToZeroVolume() {
        for (const trackName in this.trackGainNodes) {
            if (this.trackGainNodes.hasOwnProperty(trackName)) {
                this.setTrackVolume(trackName, 0);
            }
        }
    }
    
    getLoopStatus() {
        return { enabled: this._loopEnabled, start: this.loopStartSample, end: this.loopEndSample };
    }

    setStatusCallback(callback) {
        this.onStatusChange = callback;
    }

    setTrackVolume(trackName, volume) {
        if (this.trackGainNodes[trackName]) {
            const desiredVolume = Math.max(0, Math.min(1, volume));
            this.trackGainNodes[trackName].gain.value = desiredVolume;
            const track = this.tracks.find(t => t.name === trackName);
            if (track) track.currentVolume = desiredVolume;
        }
    }

    getTrackVolume(trackName) {
        const track = this.tracks.find(t => t.name === trackName);
        return track ? track.currentVolume : 0;
    }

    getTrackNames() {
        return this.tracks.map((track) => track.name);
    }
}

export { MybrPlayer };