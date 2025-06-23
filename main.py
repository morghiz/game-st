import sys
import struct
import wave
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QCheckBox,
    QSpinBox, QFileDialog, QMessageBox, QListWidget, QListWidgetItem, QGroupBox, QInputDialog
)
from PyQt6.QtCore import Qt, QBuffer, QIODevice
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from pydub import AudioSegment
import io

class MybrCreator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MYBR File Creator")
        self.setGeometry(100, 100, 700, 850)
        self.tracks = []
        self.loop_intro_file_path = None
        self.loop_segment_file_path = None
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.playbackStateChanged.connect(self.media_state_changed)
        self.media_player_playing_mybr = False
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        global_header_group = QGroupBox("Global Header")
        global_header_layout = QVBoxLayout()
        loop_enabled_layout = QHBoxLayout()
        self.loop_enabled = QCheckBox("Loop Enabled (Auto-calculated if loop files not set)")
        self.loop_enabled.setEnabled(False)
        loop_enabled_layout.addWidget(self.loop_enabled)
        loop_enabled_layout.addStretch()
        global_header_layout.addLayout(loop_enabled_layout)
        loop_intro_file_layout = QHBoxLayout()
        self.loop_intro_file_label = QLabel("Loop Intro File (defines Loop Start):")
        loop_intro_file_layout.addWidget(self.loop_intro_file_label)
        self_loop_intro_file_button = QPushButton("Load WAV for Loop Intro")
        self_loop_intro_file_button.clicked.connect(self.load_loop_intro_file)
        loop_intro_file_layout.addWidget(self_loop_intro_file_button)
        self.loop_intro_display_label = QLabel("No file loaded")
        loop_intro_file_layout.addWidget(self.loop_intro_display_label)
        loop_intro_file_layout.addStretch()
        global_header_layout.addLayout(loop_intro_file_layout)
        loop_segment_file_layout = QHBoxLayout()
        self.loop_segment_file_label = QLabel("Loop Segment File (defines Loop End offset):")
        loop_segment_file_layout.addWidget(self.loop_segment_file_label)
        self_loop_segment_file_button = QPushButton("Load WAV for Loop Segment")
        self_loop_segment_file_button.clicked.connect(self.load_loop_segment_file)
        loop_segment_file_layout.addWidget(self_loop_segment_file_button)
        self.loop_segment_display_label = QLabel("No file loaded")
        loop_segment_file_layout.addWidget(self.loop_segment_display_label)
        loop_segment_file_layout.addStretch()
        global_header_layout.addLayout(loop_segment_file_layout)
        global_header_group.setLayout(global_header_layout)
        main_layout.addWidget(global_header_group)
        tracks_group = QGroupBox("Tracks")
        tracks_layout = QVBoxLayout()
        self.track_list = QListWidget()
        self.track_list.itemClicked.connect(self.display_track_info)
        tracks_layout.addWidget(self.track_list)
        track_buttons_layout = QHBoxLayout()
        add_track_button = QPushButton("Add Track (WAV)")
        add_track_button.clicked.connect(self.add_track)
        track_buttons_layout.addWidget(add_track_button)
        remove_track_button = QPushButton("Remove Selected Track")
        remove_track_button.clicked.connect(self.remove_track)
        track_buttons_layout.addWidget(remove_track_button)
        track_buttons_layout.addStretch()
        tracks_layout.addLayout(track_buttons_layout)
        tracks_group.setLayout(tracks_layout)
        main_layout.addWidget(tracks_group)
        track_info_group = QGroupBox("Selected Track Info")
        track_info_layout = QVBoxLayout()
        self.track_name_label = QLabel("Name: ")
        track_info_layout.addWidget(self.track_name_label)
        self.track_path_label = QLabel("Path: ")
        track_info_layout.addWidget(self.track_path_label)
        self.track_channels_label = QLabel("Channels: ")
        track_info_layout.addWidget(self.track_channels_label)
        self.track_samplerate_label = QLabel("Sample Rate: ")
        track_info_layout.addWidget(self.track_samplerate_label)
        self.track_samples_label = QLabel("Number of Samples: ")
        track_info_layout.addWidget(self.track_samples_label)
        track_info_group.setLayout(track_info_layout)
        main_layout.addWidget(track_info_group)
        playback_group = QGroupBox("MYBR Playback")
        playback_layout = QHBoxLayout()
        self.load_mybr_button = QPushButton("Load & Play MYBR File")
        self.load_mybr_button.clicked.connect(self.load_and_play_mybr)
        playback_layout.addWidget(self.load_mybr_button)
        self.stop_mybr_button = QPushButton("Stop Playback")
        self.stop_mybr_button.clicked.connect(self.stop_mybr_playback)
        self.stop_mybr_button.setEnabled(False)
        playback_layout.addWidget(self.stop_mybr_button)
        playback_layout.addStretch()
        playback_group.setLayout(playback_layout)
        main_layout.addWidget(playback_group)
        main_layout.addStretch(1)
        create_button = QPushButton("Create MYBR File")
        create_button.clicked.connect(self.create_mybr_file)
        main_layout.addWidget(create_button)
        self.setLayout(main_layout)

    def load_loop_intro_file(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select WAV File for Loop Intro (defines Loop Start)", "", "WAV Files (*.wav)")
        if file_path:
            try:
                with wave.open(file_path, 'rb') as wf:
                    nframes = wf.getnframes()
                    self.loop_intro_file_path = file_path
                    self.loop_intro_display_label.setText(f"Loaded: {file_path.split('/')[-1]} ({nframes} samples)")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not read WAV file: {e}")
                self.loop_intro_file_path = None
                self.loop_intro_display_label.setText("No file loaded")
        self._update_loop_enabled_checkbox()

    def load_loop_segment_file(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select WAV File for Loop Segment (defines loop duration)", "", "WAV Files (*.wav)")
        if file_path:
            try:
                with wave.open(file_path, 'rb') as wf:
                    nframes = wf.getnframes()
                    self.loop_segment_file_path = file_path
                    self.loop_segment_display_label.setText(f"Loaded: {file_path.split('/')[-1]} ({nframes} samples)")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not read WAV file: {e}")
                self.loop_segment_file_path = None
                self.loop_segment_display_label.setText("No file loaded")
        self._update_loop_enabled_checkbox()

    def add_track(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select WAV File", "", "WAV Files (*.wav)")
        if file_path:
            track_name, ok = QInputDialog.getText(self, 'Track Name', 'Enter name for this track:')
            if ok and track_name:
                name_bytes = track_name.encode('utf-8')
                if len(name_bytes) > 255:
                    QMessageBox.warning(self, "Warning", "Track name is too long (max 255 bytes UTF-8). Please shorten it.")
                    return
                try:
                    with wave.open(file_path, 'rb') as wf:
                        channels = wf.getnchannels()
                        samplerate = wf.getframerate()
                        nframes = wf.getnframes()
                        if wf.getsampwidth() != 2:
                            QMessageBox.critical(self, "Error", "Only 16-bit WAV files are supported.")
                            return
                        wf.rewind()
                        audio_data = wf.readframes(nframes)
                    track_info = {
                        "name": track_name,
                        "path": file_path,
                        "channels": channels,
                        "samplerate": samplerate,
                        "nframes": nframes,
                        "audio_data": audio_data
                    }
                    self.tracks.append(track_info)
                    self.track_list.addItem(f"{track_name} ({file_path.split('/')[-1]})")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not read WAV file: {e}")
            elif ok and not track_name:
                QMessageBox.warning(self, "Warning", "Track name cannot be empty.")
        self._update_loop_enabled_checkbox()

    def remove_track(self):
        current_row = self.track_list.currentRow()
        if current_row != -1:
            self.track_list.takeItem(current_row)
            del self.tracks[current_row]
            self.clear_track_info()
            for i in range(self.track_list.count()):
                item = self.track_list.item(i)
                item.setText(f"{self.tracks[i]['name']} ({self.tracks[i]['path'].split('/')[-1]})")
        self._update_loop_enabled_checkbox()

    def display_track_info(self, item):
        index = self.track_list.row(item)
        if 0 <= index < len(self.tracks):
            track = self.tracks[index]
            self.track_name_label.setText(f"Name: {track['name']}")
            self.track_path_label.setText(f"Path: {track['path']}")
            self.track_channels_label.setText(f"Channels: {track['channels']}")
            self.track_samplerate_label.setText(f"Sample Rate: {track['samplerate']}")
            self.track_samples_label.setText(f"Number of Samples: {track['nframes']}")

    def clear_track_info(self):
        self.track_name_label.setText("Name: ")
        self.track_path_label.setText("Path: ")
        self.track_channels_label.setText("Channels: ")
        self.track_samplerate_label.setText("Sample Rate: ")
        self.track_samples_label.setText("Number of Samples: ")

    def _update_loop_enabled_checkbox(self):
        loop_start_samples_candidate = 0
        loop_end_samples_candidate = 0
        if self.loop_intro_file_path and self.loop_segment_file_path:
            try:
                with wave.open(self.loop_intro_file_path, 'rb') as wf_intro:
                    loop_start_samples_candidate = wf_intro.getnframes()
                with wave.open(self.loop_segment_file_path, 'rb') as wf_segment:
                    loop_segment_samples = wf_segment.getnframes()
                loop_end_samples_candidate = loop_start_samples_candidate + loop_segment_samples
                self.loop_enabled.setChecked(True)
                self.loop_enabled.setText(f"Loop Enabled (via files: Start {loop_start_samples_candidate}, End {loop_end_samples_candidate})")
            except Exception:
                self.loop_enabled.setChecked(False)
                self.loop_enabled.setText("Loop Enabled (Error reading loop files)")
        elif self.tracks:
            first_track_duration = self.tracks[0]['nframes']
            if first_track_duration > 0 and loop_start_samples_candidate == 0:
                loop_end_samples_for_check = first_track_duration
                if loop_end_samples_candidate == loop_end_samples_for_check:
                    self.loop_enabled.setChecked(True)
                    self.loop_enabled.setText(f"Loop Enabled (Auto-calculated: Start 0, End {first_track_duration})")
                else:
                    self.loop_enabled.setChecked(False)
                    self.loop_enabled.setText("Loop Enabled (Auto-calculated: No match)")
            else:
                self.loop_enabled.setChecked(False)
                self.loop_enabled.setText("Loop Enabled (No tracks or zero duration)")
        else:
            self.loop_enabled.setChecked(False)
            self.loop_enabled.setText("Loop Enabled (Auto-calculated if loop files not set)")

    def create_mybr_file(self):
        if not self.tracks:
            QMessageBox.warning(self, "Warning", "Please add at least one track.")
            return
        loop_start_samples = 0
        loop_end_samples = 0
        loop_enabled_flag = 0
        if self.loop_intro_file_path and self.loop_segment_file_path:
            try:
                with wave.open(self.loop_intro_file_path, 'rb') as wf_intro:
                    loop_start_samples = wf_intro.getnframes()
                with wave.open(self.loop_segment_file_path, 'rb') as wf_segment:
                    loop_segment_samples = wf_segment.getnframes()
                loop_end_samples = loop_start_samples + loop_segment_samples
                loop_enabled_flag = 1
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not read loop files: {e}")
                return
        else:
            if self.tracks and self.tracks[0]['nframes'] > 0:
                first_track_duration = self.tracks[0]['nframes']
                if loop_start_samples == 0 and loop_end_samples == 0:
                    loop_end_samples = first_track_duration
                if loop_start_samples == 0 and loop_end_samples == first_track_duration:
                    loop_enabled_flag = 1
                else:
                    loop_enabled_flag = 0
            else:
                loop_enabled_flag = 0
        save_path, _ = QFileDialog.getSaveFileName(self, "Save MYBR File", "", "MYBR Files (*.mybr)")
        if not save_path:
            return
        try:
            with open(save_path, 'wb') as f:
                f.write(struct.pack('<I', 0x5242594D))
                f.write(struct.pack('<B', len(self.tracks)))
                f.write(struct.pack('<B', loop_enabled_flag))
                f.write(struct.pack('<I', loop_start_samples))
                f.write(struct.pack('<I', loop_end_samples))
                track_headers_total_size = 0
                for track in self.tracks:
                    name_bytes = track['name'].encode('utf-8')
                    name_length = len(name_bytes)
                    track_headers_total_size += (1 + 4 + 4 + 1 + name_length + 4)
                current_offset = 14 + track_headers_total_size
                track_data_blocks = []
                for track in self.tracks:
                    wav_header = self._create_wav_header(
                        track['channels'],
                        track['samplerate'],
                        16,
                        track['nframes']
                    )
                    track_data_blocks.append(wav_header + track['audio_data'])
                for i, track in enumerate(self.tracks):
                    f.write(struct.pack('<B', track['channels']))
                    f.write(struct.pack('<I', track['samplerate']))
                    f.write(struct.pack('<I', track['nframes']))
                    name_bytes = track['name'].encode('utf-8')
                    name_length = len(name_bytes)
                    f.write(struct.pack('<B', name_length))
                    f.write(name_bytes)
                    f.write(struct.pack('<I', current_offset))
                    current_offset += len(track_data_blocks[i])
                for data_block in track_data_blocks:
                    f.write(data_block)
            QMessageBox.information(self, "Success", "MYBR file created successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create MYBR file: {e}")

    def _create_wav_header(self, channels, samplerate, bits_per_sample, num_frames):
        byte_rate = samplerate * channels * (bits_per_sample // 8)
        block_align = channels * (bits_per_sample // 8)
        data_size = num_frames * channels * (bits_per_sample // 8)
        chunk_size = 36 + data_size
        header = b'RIFF'
        header += struct.pack('<I', chunk_size)
        header += b'WAVE'
        header += b'fmt '
        header += struct.pack('<I', 16)
        header += struct.pack('<H', 1)
        header += struct.pack('<H', channels)
        header += struct.pack('<I', samplerate)
        header += struct.pack('<I', byte_rate)
        header += struct.pack('<H', block_align)
        header += struct.pack('<H', bits_per_sample)
        header += b'data'
        header += struct.pack('<I', data_size)
        return header

    def load_and_play_mybr(self):
        if self.media_player_playing_mybr:
            self.stop_mybr_playback()
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select MYBR File to Play", "", "MYBR Files (*.mybr)")
        if not file_path:
            return
        try:
            with open(file_path, 'rb') as f:
                magic_number = struct.unpack('<I', f.read(4))[0]
                if magic_number != 0x5242594D:
                    QMessageBox.critical(self, "Error", "Invalid MYBR file: Magic number mismatch.")
                    return
                num_tracks = struct.unpack('<B', f.read(1))[0]
                loop_enabled_flag = struct.unpack('<B', f.read(1))[0]
                loop_start_samples = struct.unpack('<I', f.read(4))[0]
                loop_end_samples = struct.unpack('<I', f.read(4))[0]
                track_headers = []
                for _ in range(num_tracks):
                    channels = struct.unpack('<B', f.read(1))[0]
                    samplerate = struct.unpack('<I', f.read(4))[0]
                    nframes = struct.unpack('<I', f.read(4))[0]
                    name_length = struct.unpack('<B', f.read(1))[0]
                    name_bytes = f.read(name_length)
                    track_name = name_bytes.decode('utf-8')
                    offset_to_data = struct.unpack('<I', f.read(4))[0]
                    track_headers.append({
                        "channels": channels,
                        "samplerate": samplerate,
                        "nframes": nframes,
                        "name": track_name,
                        "offset_to_data": offset_to_data
                    })
                all_audio_data = b''
                current_file_position = f.tell()
                for i, header in enumerate(track_headers):
                    f.seek(header["offset_to_data"])
                    wav_header_size = 44 # Standard WAV header size
                    audio_data_size = header["nframes"] * header["channels"] * 2 # 16-bit audio (2 bytes/sample)
                    full_wav_block_size = wav_header_size + audio_data_size
                    audio_block = f.read(full_wav_block_size)
                    all_audio_data += audio_block[wav_header_size:] # Extract raw audio data, skip header
                f.seek(current_file_position)

            if not track_headers:
                QMessageBox.warning(self, "Warning", "No tracks found in the MYBR file.")
                return

            first_track_samplerate = track_headers[0]["samplerate"]
            first_track_channels = track_headers[0]["channels"]

            # Convert raw audio bytes to a format pydub can understand
            # Assuming 16-bit stereo for simplicity if possible, otherwise adjust.
            # pydub needs raw PCM data for AudioSegment.from_raw
            audio_segment = AudioSegment(
                all_audio_data,
                frame_rate=first_track_samplerate,
                channels=first_track_channels,
                sample_width=2 # 16-bit audio
            )
            
            raw_audio_stream = io.BytesIO()
            audio_segment.export(raw_audio_stream, format="wav")
            raw_audio_stream.seek(0)
            
            self.audio_buffer = QBuffer()
            self.audio_buffer.setData(raw_audio_stream.read())
            self.audio_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            
            self.media_player.setSource(self.audio_buffer)
            self.media_player.play()
            self.media_player_playing_mybr = True
            self.load_mybr_button.setEnabled(False)
            self.stop_mybr_button.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load or play MYBR file: {e}")
            self.media_player_playing_mybr = False
            self.load_mybr_button.setEnabled(True)
            self.stop_mybr_button.setEnabled(False)

    def stop_mybr_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.stop()
        self.media_player_playing_mybr = False
        self.load_mybr_button.setEnabled(True)
        self.stop_mybr_button.setEnabled(False)
        if hasattr(self, 'audio_buffer') and self.audio_buffer.isOpen():
            self.audio_buffer.close()

    def media_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.stop_mybr_playback()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MybrCreator()
    window.show()
    sys.exit(app.exec())