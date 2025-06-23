#!/usr/bin/env python3
"""
MYBR Creator - Generatore di file .mybr per il riproduttore web
Applicazione PyQt6 per creare file audio multi-traccia in formato .mybr
"""

import sys
import os
import struct
import wave
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QProgressBar, QGroupBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QHeaderView, QFrame, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor


class AudioTrack:
    """Rappresenta una traccia audio con i suoi metadati"""
    def __init__(self, file_path: str, name: str = ""):
        self.file_path = file_path
        self.name = name or Path(file_path).stem
        self.channels = 0
        self.sample_rate = 0
        self.num_samples = 0
        self.duration = 0.0
        self.valid = False
        self._analyze_wav()
    
    def _analyze_wav(self):
        """Analizza il file WAV per estrarre i metadati"""
        try:
            with wave.open(self.file_path, 'rb') as wf:
                self.channels = wf.getnchannels()
                self.sample_rate = wf.getframerate()
                self.num_samples = wf.getnframes()
                self.duration = self.num_samples / self.sample_rate
                self.valid = True
        except wave.Error as e:
            print(f"Errore nell'analisi del file WAV {self.file_path}: {e}")
            self.valid = False
        except FileNotFoundError:
            print(f"File non trovato: {self.file_path}")
            self.valid = False
        except Exception as e:
            print(f"Errore generico nell'analisi WAV {self.file_path}: {e}")
            self.valid = False


class MYBRFileCreator(QThread):
    """Thread per la creazione del file .mybr"""
    progress_updated = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, tracks: List[AudioTrack], output_path: str, 
                 loop_enabled: bool, loop_mode: str, 
                 loop_start_manual: int, loop_end_manual: int,
                 loop_start_file_path: Optional[str], loop_end_file_path: Optional[str]):
        super().__init__()
        self.tracks = tracks
        self.output_path = output_path
        self.loop_enabled = loop_enabled
        self.loop_mode = loop_mode # 'manual' or 'file_based'
        self.loop_start_manual = loop_start_manual
        self.loop_end_manual = loop_end_manual
        self.loop_start_file_path = loop_start_file_path
        self.loop_end_file_path = loop_end_file_path
        self.magic_number = 0x5242594D # 'MYBR'

    def run(self):
        """Esegue la creazione del file MYBR"""
        try:
            self.progress_updated.emit(0, "Inizio creazione file MYBR...")

            if not self.tracks:
                raise ValueError("Nessuna traccia audio da elaborare.")
            
            loop_start_sample = 0
            loop_end_sample = 0

            if self.loop_enabled:
                if self.loop_mode == 'manual':
                    loop_start_sample = self.loop_start_manual
                    loop_end_sample = self.loop_end_manual
                elif self.loop_mode == 'file_based':
                    if not self.loop_start_file_path or not self.loop_end_file_path:
                        raise ValueError("Selezionare i file per Loop Start e Loop End in modalità file.")
                    
                    start_track = AudioTrack(self.loop_start_file_path)
                    end_track = AudioTrack(self.loop_end_file_path)

                    if not start_track.valid or not end_track.valid:
                        raise ValueError("I file di riferimento per il loop non sono WAV validi.")
                    
                    loop_start_sample = start_track.num_samples
                    loop_end_sample = end_track.num_samples

                if loop_start_sample >= loop_end_sample:
                    raise ValueError("Loop Start deve essere minore di Loop End.")
                if loop_end_sample > self.tracks[0].num_samples:
                    # Assumiamo che il loop si riferisca alla durata della traccia principale (la prima)
                    raise ValueError(f"Loop End ({loop_end_sample}) non può superare la durata della prima traccia ({self.tracks[0].num_samples} campioni).")

            with open(self.output_path, 'wb') as output_file:
                # 1. Scrittura Global Header
                # Magic Number (4 bytes)
                output_file.write(struct.pack('<I', self.magic_number))
                # Numero di tracce (1 byte)
                output_file.write(struct.pack('<B', len(self.tracks)))
                # Loop abilitato (1 byte)
                output_file.write(struct.pack('<B', 1 if self.loop_enabled else 0))
                # Loop Start Sample (4 bytes)
                output_file.write(struct.pack('<I', loop_start_sample))
                # Loop End Sample (4 bytes)
                output_file.write(struct.pack('<I', loop_end_sample))

                # Calcola gli offset dei dati audio
                header_size = 4 + 1 + 1 + 4 + 4 # Global Header size
                
                # Dimensione di tutti i Track Headers
                track_headers_size = 0
                for track in self.tracks:
                    # channels (1) + sample_rate (4) + num_samples (4) + name_length (1) + name (N) + offset_to_data (4)
                    track_headers_size += (1 + 4 + 4 + 1 + len(track.name.encode('utf-8')) + 4)

                current_offset = header_size + track_headers_size
                track_data_offsets = []
                
                for i, track in enumerate(self.tracks):
                    wav_data_size = self._get_wav_data_size(track.file_path)
                    track_data_offsets.append(current_offset)
                    current_offset += wav_data_size
                    self.progress_updated.emit(int((i / len(self.tracks)) * 50), f"Calcolo offset traccia {i+1}/{len(self.tracks)}")

                # 2. Scrittura Track Headers
                for i, track in enumerate(self.tracks):
                    # Canali (1 byte)
                    output_file.write(struct.pack('<B', track.channels))
                    # Sample Rate (4 bytes)
                    output_file.write(struct.pack('<I', track.sample_rate))
                    # Numero Campioni (4 bytes)
                    output_file.write(struct.pack('<I', track.num_samples))
                    
                    # Nome Traccia (lunghezza 1 byte, poi stringa UTF-8)
                    name_bytes = track.name.encode('utf-8')
                    if len(name_bytes) > 255:
                        raise ValueError(f"Nome traccia '{track.name}' troppo lungo (max 255 bytes UTF-8).")
                    output_file.write(struct.pack('<B', len(name_bytes)))
                    output_file.write(name_bytes)

                    # Offset ai dati audio (4 bytes)
                    output_file.write(struct.pack('<I', track_data_offsets[i]))
                    self.progress_updated.emit(50 + int((i / len(self.tracks)) * 25), f"Scrittura header traccia {i+1}/{len(self.tracks)}")


                # 3. Scrittura Dati Audio
                for i, track in enumerate(self.tracks):
                    self._write_wav_data(track.file_path, output_file)
                    self.progress_updated.emit(75 + int((i / len(self.tracks)) * 25), f"Scrittura dati traccia {i+1}/{len(self.tracks)}")

            self.finished_signal.emit(True, f"File MYBR creato con successo: {self.output_path}")

        except Exception as e:
            self.finished_signal.emit(False, f"Errore durante la creazione del file MYBR: {e}")

    def _get_wav_data_size(self, wav_path: str) -> int:
        """Restituisce la dimensione in byte del file WAV completo."""
        return os.path.getsize(wav_path)

    def _write_wav_data(self, wav_path: str, output_file):
        """Scrive il contenuto binario di un file WAV nell'output."""
        with open(wav_path, 'rb') as wav_file:
            output_file.write(wav_file.read())


class MYBRCreatorMainWindow(QMainWindow):
    """Finestra principale dell'applicazione MYBR Creator"""
    def __init__(self):
        super().__init__()
        self.tracks: List[AudioTrack] = []
        self.creator_thread: Optional[MYBRFileCreator] = None
        self.init_ui()

    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        self.setWindowTitle("MYBR Creator")
        self.setGeometry(100, 100, 800, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Stile Dark Mode
        self.set_dark_theme()

        # Gruppo selezione tracce
        track_group = QGroupBox("Tracce Audio")
        track_layout = QVBoxLayout(track_group)
        
        add_remove_layout = QHBoxLayout()
        self.add_track_btn = QPushButton("Aggiungi Traccia WAV")
        self.add_track_btn.clicked.connect(self.add_track)
        self.remove_track_btn = QPushButton("Rimuovi Traccia Selezionata")
        self.remove_track_btn.clicked.connect(self.remove_selected_track)
        add_remove_layout.addWidget(self.add_track_btn)
        add_remove_layout.addWidget(self.remove_track_btn)
        track_layout.addLayout(add_remove_layout)

        self.track_table = QTableWidget()
        self.track_table.setColumnCount(5)
        self.track_table.setHorizontalHeaderLabels(["Nome", "Percorso File", "Canali", "Sample Rate", "Durata (s)"])
        self.track_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.track_table.itemChanged.connect(self.on_track_item_changed)
        track_layout.addWidget(self.track_table)
        main_layout.addWidget(track_group)

        # Gruppo impostazioni loop
        loop_group = QGroupBox("Impostazioni Loop")
        loop_layout = QVBoxLayout(loop_group)
        
        self.loop_enabled_cb = QCheckBox("Abilita Loop")
        self.loop_enabled_cb.stateChanged.connect(self.toggle_loop_inputs)
        loop_layout.addWidget(self.loop_enabled_cb)

        # Scelta modalità loop
        loop_mode_layout = QHBoxLayout()
        self.loop_mode_manual_cb = QCheckBox("Manuale (Campioni)")
        self.loop_mode_manual_cb.setChecked(True)
        self.loop_mode_manual_cb.toggled.connect(self.toggle_loop_mode)
        self.loop_mode_file_cb = QCheckBox("Basato su File WAV")
        self.loop_mode_file_cb.toggled.connect(self.toggle_loop_mode)
        loop_mode_layout.addWidget(self.loop_mode_manual_cb)
        loop_mode_layout.addWidget(self.loop_mode_file_cb)
        loop_layout.addLayout(loop_mode_layout)

        # Input manuale (campioni)
        self.manual_loop_frame = QFrame()
        self.manual_loop_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.manual_loop_frame.setFrameShadow(QFrame.Shadow.Raised)
        manual_loop_layout = QVBoxLayout(self.manual_loop_frame)
        
        loop_start_layout = QHBoxLayout()
        loop_start_layout.addWidget(QLabel("Loop Start (Campioni):"))
        self.loop_start_spin = QSpinBox()
        self.loop_start_spin.setRange(0, 2**31 - 1) # Max for Uint32
        loop_start_layout.addWidget(self.loop_start_spin)
        manual_loop_layout.addLayout(loop_start_layout)

        loop_end_layout = QHBoxLayout()
        loop_end_layout.addWidget(QLabel("Loop End (Campioni):"))
        self.loop_end_spin = QSpinBox()
        self.loop_end_spin.setRange(0, 2**31 - 1) # Max for Uint32
        loop_end_layout.addWidget(self.loop_end_spin)
        manual_loop_layout.addLayout(loop_end_layout)
        loop_layout.addWidget(self.manual_loop_frame)

        # Input basato su file
        self.file_loop_frame = QFrame()
        self.file_loop_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.file_loop_frame.setFrameShadow(QFrame.Shadow.Raised)
        file_loop_layout = QVBoxLayout(self.file_loop_frame)

        loop_start_file_layout = QHBoxLayout()
        loop_start_file_layout.addWidget(QLabel("File Loop Start:"))
        self.loop_start_file_edit = QLineEdit()
        self.loop_start_file_edit.setPlaceholderText("Seleziona file WAV per Loop Start")
        self.browse_loop_start_file_btn = QPushButton("Sfoglia...")
        self.browse_loop_start_file_btn.clicked.connect(self.browse_loop_start_file)
        loop_start_file_layout.addWidget(self.loop_start_file_edit)
        loop_start_file_layout.addWidget(self.browse_loop_start_file_btn)
        file_loop_layout.addLayout(loop_start_file_layout)

        loop_end_file_layout = QHBoxLayout()
        loop_end_file_layout.addWidget(QLabel("File Loop End:"))
        self.loop_end_file_edit = QLineEdit()
        self.loop_end_file_edit.setPlaceholderText("Seleziona file WAV per Loop End")
        self.browse_loop_end_file_btn = QPushButton("Sfoglia...")
        self.browse_loop_end_file_btn.clicked.connect(self.browse_loop_end_file)
        loop_end_file_layout.addWidget(self.loop_end_file_edit)
        loop_end_file_layout.addWidget(self.browse_loop_end_file_btn)
        file_loop_layout.addLayout(loop_end_file_layout)
        loop_layout.addWidget(self.file_loop_frame)
        
        self.toggle_loop_inputs() # Imposta lo stato iniziale
        self.toggle_loop_mode() # Imposta lo stato iniziale della modalità loop
        main_layout.addWidget(loop_group)

        # Gruppo output
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)

        output_path_layout = QHBoxLayout()
        output_path_layout.addWidget(QLabel("Salva come:"))
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Seleziona dove salvare il file .mybr")
        # Imposta un percorso predefinito, es. nella home dell'utente
        self.output_path_edit.setText(os.path.join(os.path.expanduser("~"), "output.mybr"))
        self.browse_output_btn = QPushButton("Sfoglia...")
        self.browse_output_btn.clicked.connect(self.browse_output_path)
        output_path_layout.addWidget(self.output_path_edit)
        output_path_layout.addWidget(self.browse_output_btn)
        output_layout.addLayout(output_path_layout)
        
        self.create_btn = QPushButton("Crea File MYBR")
        self.create_btn.clicked.connect(self.create_mybr_file)
        output_layout.addWidget(self.create_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        output_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Pronto")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        output_layout.addWidget(self.status_label)

        main_layout.addWidget(output_group)
        main_layout.addStretch(1)

    def set_dark_theme(self):
        """Imposta un tema scuro per l'applicazione"""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        
        # Colori per i controlli (QSpinBox, QLineEdit, QProgressBar)
        palette.setColor(QPalette.ColorGroup.Normal, QPalette.ColorRole.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorGroup.Normal, QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorGroup.Normal, QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorGroup.Normal, QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

        # Disabilitato
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(128, 128, 128))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(128, 128, 128))
        
        self.setPalette(palette)
        QApplication.instance().setPalette(palette)

        # Applica stili ai QGroupBox
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                margin-top: 10px;
                border: 1px solid #3a3a3a;
                border-radius: 5px;
                padding-top: 15px;
                padding-left: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px;
                color: #ADD8E6; /* Light Blue for titles */
            }
            QTableWidget {
                alternate-background-color: #323232;
                background-color: #2a2a2a;
                selection-background-color: #4285F4; /* Google Blue */
                color: #FFFFFF;
                gridline-color: #555555;
            }
            QHeaderView::section {
                background-color: #444444;
                color: #FFFFFF;
                padding: 4px;
                border: 1px solid #555555;
            }
            QPushButton {
                background-color: #4CAF50; /* Green */
                color: white;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #606060;
                color: #b0b0b0;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
                background-color: #3a3a3a;
                color: #FFFFFF;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 5px;
                text-align: center;
                color: #FFFFFF;
                background-color: #3a3a3a;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
            QCheckBox {
                color: #FFFFFF;
            }
            QLabel {
                color: #FFFFFF;
            }
            QFrame {
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 5px;
                margin-top: 5px;
                background-color: #323232;
            }
        """)

    def add_track(self):
        """Apre un dialogo per aggiungere un file WAV come traccia"""
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Seleziona File Audio WAV", "", "File WAV (*.wav)")
        if file_paths:
            for file_path in file_paths:
                track = AudioTrack(file_path)
                if track.valid:
                    self.tracks.append(track)
                    self.update_track_table()
                else:
                    QMessageBox.warning(self, "File non valido", f"Il file '{Path(file_path).name}' non è un WAV valido o è corrotto.")

    def remove_selected_track(self):
        """Rimuove la traccia selezionata dalla tabella"""
        selected_rows = self.track_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Nessuna selezione", "Seleziona una riga da rimuovere.")
            return

        rows_to_remove = sorted([index.row() for index in selected_rows], reverse=True)
        for row in rows_to_remove:
            self.track_table.removeRow(row)
            del self.tracks[row]
        self.update_track_table()

    def update_track_table(self):
        """Aggiorna la tabella delle tracce con i dati correnti"""
        self.track_table.setRowCount(len(self.tracks))
        for i, track in enumerate(self.tracks):
            name_item = QTableWidgetItem(track.name)
            name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable) # Rendi il nome modificabile
            self.track_table.setItem(i, 0, name_item)
            self.track_table.setItem(i, 1, QTableWidgetItem(track.file_path))
            self.track_table.setItem(i, 2, QTableWidgetItem(str(track.channels)))
            self.track_table.setItem(i, 3, QTableWidgetItem(str(track.sample_rate)))
            self.track_table.setItem(i, 4, QTableWidgetItem(f"{track.duration:.2f}"))
            
            # Rendi le colonne non modificabili tranne il nome
            for col in range(1, self.track_table.columnCount()):
                item = self.track_table.item(i, col)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        # Aggiorna il valore massimo di loop_end_spin se ci sono tracce
        if self.tracks:
            # Il massimo per il loop end manuale dovrebbe essere la lunghezza della prima traccia
            self.loop_end_spin.setMaximum(self.tracks[0].num_samples)
        else:
            self.loop_end_spin.setMaximum(2**31 - 1) # Reset a max Uint32

    def on_track_item_changed(self, item: QTableWidgetItem):
        """Gestisce il cambio di un elemento nella tabella (es. nome traccia)"""
        if item.column() == 0: # Se il nome della traccia è stato modificato
            row = item.row()
            if 0 <= row < len(self.tracks):
                new_name = item.text()
                if not new_name:
                    QMessageBox.warning(self, "Nome Traccia", "Il nome della traccia non può essere vuoto. Ripristino al nome precedente.")
                    item.setText(self.tracks[row].name) # Ripristina il nome
                elif len(new_name.encode('utf-8')) > 255:
                    QMessageBox.warning(self, "Nome Traccia", "Il nome della traccia è troppo lungo (max 255 caratteri UTF-8). Verrà troncato nel file MYBR.")
                    self.tracks[row].name = new_name # Salva il nome intero, il creatore lo troncherà
                else:
                    self.tracks[row].name = new_name

    def toggle_loop_inputs(self):
        """Abilita/disabilita i campi di input del loop in base alla checkbox principale"""
        enabled = self.loop_enabled_cb.isChecked()
        self.loop_mode_manual_cb.setEnabled(enabled)
        self.loop_mode_file_cb.setEnabled(enabled)
        
        # Riapplica la logica di visibilità delle cornici in base alla modalità selezionata
        self.toggle_loop_mode()

    def toggle_loop_mode(self):
        """Alterna tra input manuale e basato su file per il loop"""
        manual_mode_enabled = self.loop_mode_manual_cb.isChecked() and self.loop_enabled_cb.isChecked()
        file_mode_enabled = self.loop_mode_file_cb.isChecked() and self.loop_enabled_cb.isChecked()

        self.manual_loop_frame.setVisible(manual_mode_enabled)
        self.file_loop_frame.setVisible(file_mode_enabled)

        # Sincronizza le checkbox di modalità
        if self.sender() == self.loop_mode_manual_cb and self.loop_mode_manual_cb.isChecked():
            self.loop_mode_file_cb.setChecked(False)
        elif self.sender() == self.loop_mode_file_cb and self.loop_mode_file_cb.isChecked():
            self.loop_mode_manual_cb.setChecked(False)
        
        # Se nessuna delle due è selezionata, forziamo la selezione di "Manuale"
        if self.loop_enabled_cb.isChecked() and not self.loop_mode_manual_cb.isChecked() and not self.loop_mode_file_cb.isChecked():
             self.loop_mode_manual_cb.setChecked(True) # Default a manuale


    def browse_loop_start_file(self):
        """Seleziona il file WAV per il Loop Start"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleziona File WAV per Loop Start", "", "File WAV (*.wav)")
        if file_path:
            self.loop_start_file_edit.setText(file_path)

    def browse_loop_end_file(self):
        """Seleziona il file WAV per il Loop End"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleziona File WAV per Loop End", "", "File WAV (*.wav)")
        if file_path:
            self.loop_end_file_edit.setText(file_path)


    def browse_output_path(self):
        """Apre un dialogo per selezionare il percorso di output"""
        file_path, _ = QFileDialog.getSaveFileName(self, "Salva File MYBR", self.output_path_edit.text(), "File MYBR (*.mybr)")
        if file_path:
            # Assicurati che l'estensione .mybr sia presente
            if not file_path.lower().endswith(".mybr"):
                file_path += ".mybr"
            self.output_path_edit.setText(file_path)

    def create_mybr_file(self):
        """Avvia la creazione del file MYBR in un thread separato"""
        if not self.tracks:
            QMessageBox.warning(self, "Attenzione", "Aggiungere almeno una traccia audio prima di creare il file MYBR.")
            return

        output_path = self.output_path_edit.text()
        if not output_path:
            QMessageBox.warning(self, "Percorso Output", "Selezionare un percorso di output per il file MYBR.")
            return
        
        loop_enabled = self.loop_enabled_cb.isChecked()
        loop_mode = 'manual' if self.loop_mode_manual_cb.isChecked() else 'file_based'
        loop_start_manual = self.loop_start_spin.value()
        loop_end_manual = self.loop_end_spin.value()
        loop_start_file_path = self.loop_start_file_edit.text()
        loop_end_file_path = self.loop_end_file_edit.text()

        # Validazione dei valori di loop prima di passare al thread (parziale, la completa è nel thread)
        if loop_enabled:
            if loop_mode == 'manual':
                if loop_start_manual >= loop_end_manual:
                    QMessageBox.warning(self, "Errore Loop", "Loop Start deve essere minore di Loop End.")
                    return
                if self.tracks and loop_end_manual > self.tracks[0].num_samples:
                    QMessageBox.warning(self, "Errore Loop", f"Loop End ({loop_end_manual}) non può superare la durata della prima traccia ({self.tracks[0].num_samples} campioni).")
                    return
            elif loop_mode == 'file_based':
                if not loop_start_file_path or not loop_end_file_path:
                    QMessageBox.warning(self, "Errore Loop", "Selezionare entrambi i file per Loop Start e Loop End in modalità file.")
                    return
                # Ulteriore validazione dei file WAV avverrà nel thread per evitare blocchi UI
        
        self.create_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("In creazione...")

        self.creator_thread = MYBRFileCreator(
            self.tracks,
            output_path,
            loop_enabled,
            loop_mode,
            loop_start_manual,
            loop_end_manual,
            loop_start_file_path,
            loop_end_file_path
        )
        
        self.creator_thread.progress_updated.connect(self.on_progress_updated)
        self.creator_thread.finished_signal.connect(self.on_creation_finished)
        self.creator_thread.start()
    
    def on_progress_updated(self, value: int, message: str):
        """Aggiorna il progresso"""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
    
    def on_creation_finished(self, success: bool, message: str):
        """Gestisce il completamento della creazione"""
        self.create_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(message)
        
        if success:
            QMessageBox.information(self, "Successo", message)
        else:
            QMessageBox.critical(self, "Errore", message)
        
        self.creator_thread = None


def main():
    """Funzione principale"""
    app = QApplication(sys.argv)
    app.setApplicationName("MYBR Creator")
    app.setOrganizationName("MYBR Tools")
    
    # Imposta l'icona dell'applicazione se disponibile
    # try:
    #     app_icon = QIcon("icon.png") # Assicurati che 'icon.png' sia nella stessa directory
    #     app.setWindowIcon(app_icon)
    # except Exception:
    #     pass # Nessuna icona, continua senza

    window = MYBRCreatorMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()