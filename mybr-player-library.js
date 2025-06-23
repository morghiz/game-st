class MybrPlayer extends EventTarget {
    constructor() {
        super();
        this.audioContext = null;
        this._mainGainNode = null;
        this.tracks = [];
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
            if (track.sourceNode) track.sourceNode.loop = this._loopEnabled;
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
        if (!this.audioContext || this.tracks.length === 0 || !this.tracks[0].audioBuffer) return this._pausedTime;
        if (!this._isPlaying) return this._pausedTime;
        const elapsed = this.audioContext.currentTime - this._playbackStartTime;
        let current = this._pausedTime + elapsed;

        if (this._loopEnabled && this.loopEndSample > this.loopStartSample && current >= (this.loopEndSample / this.tracks[0].audioBuffer.sampleRate)) {
            const loopStartSec = this.loopStartSample / this.tracks[0].audioBuffer.sampleRate;
            const loopEndSec = this.loopEndSample / this.tracks[0].audioBuffer.sampleRate;
            const loopDuration = loopEndSec - loopStartSec;
            if (loopDuration > 0) {
                current = loopStartSec + ((current - loopStartSec) % loopDuration);
            }
        }
        return current;
    }

    set src(url) {
        if (this._src === url) return;
        this._src = url;
        this.stop();
        this._loadingPromise = this._fetchAndParseAudio(url);
        this.dispatchEvent(new Event('loadstart'));
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
            const arrayBuffer = await response.arrayBuffer();

            const dataView = new DataView(arrayBuffer);
            let offset = 0;

            const magicNumber = dataView.getUint32(offset, true); offset += 4;
            const numTracks = dataView.getUint8(offset); offset += 1;
            this._loopEnabled = dataView.getUint8(offset) === 1; offset += 1; 
            this.loopStartSample = dataView.getUint32(offset, true); offset += 4;
            this.loopEndSample = dataView.getUint32(offset, true); offset += 4;

            const EXPECTED_MAGIC_NUMBER = 0x5242594D; // 'MYBR'
            if (magicNumber !== EXPECTED_MAGIC_NUMBER) {
                this.onStatusChange(`Errore: Numero Magico non valido. Trovato: 0x${magicNumber.toString(16)}. Atteso: 0x${EXPECTED_MAGIC_NUMBER.toString(16)}.`, this._loopEnabled);
                throw new Error('Numero Magico non valido');
            }

            if (!this.audioContext) this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.tracks = [];

            const trackHeaders = [];

            for (let i = 0; i < numTracks; i++) {
                const channels = dataView.getUint8(offset); offset += 1;
                const sampleRate = dataView.getUint32(offset, true); offset += 4;
                const numSamples = dataView.getUint32(offset, true); offset += 4;
                
                // --- NUOVA PARTE PER IL NOME DELLA TRACCIA (lettura) ---
                const nameLength = dataView.getUint8(offset); offset += 1; // Lunghezza del nome (1 byte)
                const nameBytes = new Uint8Array(arrayBuffer, offset, nameLength);
                const trackName = new TextDecoder().decode(nameBytes); // Decodifica la stringa
                offset += nameLength;
                // --- FINE NUOVA PARTE ---

                const offsetToData = dataView.getUint32(offset, true); offset += 4;

                trackHeaders.push({ channels, sampleRate, numSamples, trackName, offsetToData });
            }

            const decodePromises = trackHeaders.map(async (header, index) => {
                const wavBuffer = arrayBuffer.slice(header.offsetToData);
                
                if (wavBuffer.byteLength === 0) {
                    console.warn(`Traccia ${index}: Nessun dato audio presente.`);
                    return null;
                }

                try {
                    const audioBuffer = await this.audioContext.decodeAudioData(wavBuffer);
                    return { 
                        audioBuffer, 
                        currentVolume: (index === 0) ? 1.0 : 0.0, 
                        name: header.trackName || `Traccia ${index + 1}`, // Usa il nome letto o un fallback
                        path: url + `#track${index}` 
                    }; 
                } catch (e) {
                    console.error(`Errore durante la decodifica della traccia ${index}:`, e);
                    return null;
                }
            });

            const decodedTracks = await Promise.all(decodePromises);
            this.tracks = decodedTracks.filter(track => track !== null);

            if (this.tracks.length === 0) {
                throw new Error("Nessuna traccia audio valida è stata caricata.");
            }

            this.onStatusChange('Pronto', this._loopEnabled);
            return { loopEnabled: this._loopEnabled, loopStartSample: this.loopStartSample, loopEndSample: this.loopEndSample };

        } catch (e) {
            this.tracks = [];
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
        this._pausedTime = this.currentTime;
        this.tracks.forEach(track => {
            if (track.sourceNode) {
                track.sourceNode.stop();
                track.sourceNode.disconnect();
                track.sourceNode = null;
            }
        });
        this._isPlaying = false;
        this.onStatusChange('In pausa', this._loopEnabled);
        this.dispatchEvent(new Event('pause'));
    }

    stop() {
        const wasPlaying = this._isPlaying;
        this.tracks.forEach(track => {
            if (track.sourceNode) {
                track.sourceNode.stop();
                track.sourceNode.disconnect();
                track.sourceNode = null;
            }
        });
        this._isPlaying = false;
        this._pausedTime = 0;
        this._playbackStartTime = 0;
        this.onStatusChange('Fermo', this._loopEnabled);
        if (wasPlaying) this.dispatchEvent(new Event('ended'));
    }

    _startPlayback() {
        if (!this._mainGainNode) {
            this._mainGainNode = this.audioContext.createGain();
            this._mainGainNode.gain.value = this._volume;
            this._mainGainNode.connect(this.audioContext.destination);
        }

        this.tracks.forEach((track) => {
            if (track.sourceNode) {
                track.sourceNode.stop();
                track.sourceNode.disconnect();
            }
            track.sourceNode = this.audioContext.createBufferSource();
            track.sourceNode.buffer = track.audioBuffer;
            
            track.sourceNode.loop = this._loopEnabled;
            track.sourceNode.loopStart = this.loopStartSample / track.audioBuffer.sampleRate;
            track.sourceNode.loopEnd = this.loopEndSample / track.audioBuffer.sampleRate;
            
            if (!track.gainNode) {
                track.gainNode = this.audioContext.createGain();
            }
            
            track.gainNode.gain.value = track.currentVolume;
            
            track.sourceNode.connect(track.gainNode);
            track.gainNode.connect(this._mainGainNode);

            track.sourceNode.start(0, this._pausedTime);

            track.sourceNode.onended = () => {
                if (!this._loopEnabled && this._isPlaying) {
                    const allTracksEnded = this.tracks.every(t => 
                        !t.sourceNode || 
                        t.sourceNode.playbackState === AudioBufferSourceNode.ENDED_STATE ||
                        t.sourceNode.buffer === null
                    );
                    if (allTracksEnded) {
                         this.stop();
                    }
                }
            };
        });

        this._playbackStartTime = this.audioContext.currentTime - this._pausedTime;
        this._isPlaying = true;
    }

    getLoopStatus() {
        return { enabled: this._loopEnabled, start: this.loopStartSample, end: this.loopEndSample };
    }

    setStatusCallback(callback) {
        this.onStatusChange = callback;
    }

    setTrackVolume(trackIndex, volume) {
        if (trackIndex >= 0 && trackIndex < this.tracks.length) {
            this.tracks[trackIndex].currentVolume = Math.max(0, Math.min(1, volume));
            if (this.tracks[trackIndex].gainNode) {
                this.tracks[trackIndex].gainNode.gain.value = this.tracks[trackIndex].currentVolume;
            }
        }
    }

    getTrackVolume(trackIndex) {
        if (trackIndex >= 0 && trackIndex < this.tracks.length) {
            return this.tracks[trackIndex].currentVolume;
        }
        return 0;
    }

    getTrackNames() {
        // Ora usa direttamente la proprietà 'name' letta dal file
        return this.tracks.map((track, index) => track.name || `Traccia ${index + 1}`);
    }
}

export { MybrPlayer };