# Panoramica sul Funzionamento Generale del Progetto MYBR

Il progetto MYBR è un sistema a due componenti principali: un **creatore di file offline** (Python) e un **riproduttore web online** (JavaScript/HTML). L'obiettivo è permettere la creazione di brani audio multi-traccia composti da singoli file WAV, confezionandoli in un formato binario ottimizzato per il web, e quindi riprodurli efficacemente in un browser.

### 1. Architettura Generale

Il sistema è suddiviso in due macro-aree che operano in momenti e contesti diversi:

* **Offline - Strumento di Creazione (`mybr_creator.py`):**
    * **Ruolo:** Prende in input file audio WAV multipli, raccoglie metadati (nomi, impostazioni di loop) e li assembla in un unico file binario `.mybr`.
    * **Tecnologia:** Python con GUI PyQt6.
    * **Output:** File `.mybr`.

* **Online - Riproduttore Web (`index.html` + `mybr-player-library.js`):**
    * **Ruolo:** Carica il file `.mybr` generato, lo decodifica e gestisce la riproduzione sincronizzata delle tracce audio, con controlli interattivi.
    * **Tecnologia:** HTML, JavaScript (Web Audio API), CSS (TailwindCSS).
    * **Input:** File `.mybr`.

### 2. Flusso di Lavoro Dettagliato

#### A. Fase di Creazione (Offline)

1.  **Input Audio Sorgente:** L'utente fornisce uno o più file audio in formato `.wav`. È fondamentale che questi siano già nel formato desiderato (es. 16-bit PCM), poiché lo script Python non esegue ricodifiche complesse, ma estrae solo i dati audio grezzi e ricrea un header WAV minimale.
2.  **Acquisizione Metadati:**
    * Per ogni file WAV aggiunto, l'utente inserisce un **nome traccia** (es. "Batteria", "Voce", "Basso"). Questo nome è cruciale per l'identificazione lato riproduttore.
    * Vengono estratti automaticamente dal WAV i dati tecnici della traccia: numero di canali, sample rate, e numero di campioni.
3.  **Gestione del Loop:**
    * L'utente può definire un'area di loop specificando due file WAV ausiliari: un "Loop Intro File" e un "Loop Segment File". Le loro durate (in campioni) vengono usate per calcolare `loopStartSample` e `loopEndSample` del brano complessivo.
    * Se non vengono specificati file di loop, lo script verifica una condizione predefinita (loop da 0 alla fine della prima traccia) per abilitare un loop automatico. Questo flag e i campioni di inizio/fine vengono salvati nel file `.mybr`.
4.  **Assemblaggio del File `.mybr`:**
    * **Global Header:** Viene scritto un header iniziale con un "Magic Number" (`MYBR`), il numero totale di tracce, il flag di loop e i valori di `loopStartSample`/`loopEndSample`.
    * **Track Headers:** Per ogni traccia, viene scritto un header specifico che include:
        * Canali, Sample Rate, Numero Campioni (letti dal WAV).
        * **Lunghezza del Nome della Traccia (1 byte)** e il **Nome della Traccia (UTF-8)**: Questa è la chiave per l'identificazione lato client.
        * **Offset ai Dati Audio:** Questo è un puntatore (in byte) che indica dove, all'interno dello stesso file `.mybr`, iniziano i dati audio effettivi (con il loro mini-header WAV) per quella specifica traccia. Questo permette al riproduttore di "saltare" direttamente ai dati desiderati.
    * **Dati Audio:** Successivamente a tutti gli header, vengono scritti, in sequenza, i dati audio di ciascuna traccia. Ogni blocco di dati audio include un piccolo header WAV standard seguito dai dati PCM grezzi estratti dal file WAV originale.
5.  **Output:** Il risultato è un singolo file `.mybr` che incapsula tutte le tracce e i metadati in un formato binario ottimizzato per il parsing lato client.

#### B. Fase di Riproduzione (Online)

1.  **Caricamento del File (`index.html` e `mybr-player-library.js`):**
    * L'utente, tramite l'interfaccia HTML (`index.html`), seleziona un file `.mybr`.
    * Il browser legge il file come un `ArrayBuffer`.
    * La libreria `mybr-player-library.js` (la classe `MybrPlayer`) entra in azione.

2.  **Parsing e Decodifica:**
    * `MybrPlayer` utilizza `DataView` per leggere il `ArrayBuffer` e interpretare il formato `.mybr`.
    * **Global Header:** Viene letto il Magic Number per la validazione, il numero di tracce e le impostazioni di loop (`loopEnabled`, `loopStartSample`, `loopEndSample`).
    * **Track Headers:** Per ogni traccia, `MybrPlayer` legge i metadati: canali, sample rate, numero di campioni, **la lunghezza del nome e il nome della traccia stesso**, e l'offset ai dati audio.
    * **Estrazione Dati Audio:** Usando l'`offsetToData` per ogni traccia, `MybrPlayer` estrae il sotto-buffer corrispondente ai dati WAV di quella traccia.
    * **Decodifica Web Audio API:** `MybrPlayer` passa questi sotto-buffer (che contengono un header WAV seguito dai dati audio PCM) a `AudioContext.decodeAudioData()`. Questa funzione nativa del browser decodifica il formato WAV in un `AudioBuffer` utilizzabile dall'API Web Audio.

3.  **Gestione della Riproduzione (Web Audio API):**
    * **AudioContext:** Viene inizializzato un `AudioContext`, che è il motore audio del browser.
    * **Nodi Audio:** Per ogni `AudioBuffer` decodificato (ogni traccia):
        * Viene creato un `AudioBufferSourceNode`, che è responsabile della riproduzione dell'`AudioBuffer`.
        * Viene creato un `GainNode` per controllare il volume individuale di quella traccia.
        * Tutti i `GainNode` delle singole tracce sono collegati a un `_mainGainNode` (Gain master del player), che a sua volta è collegato all'output finale dell'`AudioContext` (altoparlanti).
    * **Sincronizzazione e Loop:**
        * Quando la riproduzione inizia (`play()`), tutti gli `AudioBufferSourceNode` vengono avviati contemporaneamente (o ripresi dal punto di pausa).
        * Le proprietà `loop`, `loopStart` e `loopEnd` degli `AudioBufferSourceNode` vengono impostate in base ai valori letti dal file `.mybr` e alle impostazioni runtime dell'utente. Questo garantisce un looping preciso a livello di campione.
    * **Controlli UI:** L'`index.html` fornisce slider per il volume master e per ogni singola traccia, permettendo all'utente di mixare il brano in tempo reale. I nomi delle tracce vengono recuperati dalla libreria JS e visualizzati, migliorando l'usabilità.
    * **Stato e Feedback:** La libreria `MybrPlayer` espone eventi e un callback di stato (`onStatusChange`) per permettere all'interfaccia HTML di aggiornare dinamicamente il testo di stato, il tempo corrente e altre informazioni.

### 3. Vantaggi del Design

* **Compattezza:** Un singolo file `.mybr` contiene tutte le tracce, semplificando la distribuzione.
* **Efficienza di Caricamento:** Il formato binario è più veloce da leggere rispetto a file XML/JSON testuali di grandi dimensioni. Gli offset diretti permettono un accesso rapido ai dati.
* **Nomi Tracce:** L'inclusione dei nomi delle tracce nel file stesso rende il player web auto-sufficiente per l'identificazione, senza bisogno di metadati esterni.
* **Controllo Granulare:** La Web Audio API permette un controllo preciso sul volume di ogni traccia e sul looping a livello di campione.
* **Separazione delle Responsabilità:** Il creatore Python si occupa della fase di preparazione dei dati, mentre la libreria JS si concentra sulla riproduzione, rendendo entrambi i componenti più gestibili.