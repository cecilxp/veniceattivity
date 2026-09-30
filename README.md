# Annunci bar e ristoranti – Venezia isola → Telegram

Ogni due ore GitHub controlla questi siti e ti manda su Telegram **un messaggio solo quando ci sono annunci nuovi** (se non c'è niente di nuovo, silenzio) di cessione di bar, ristoranti, bacari, pizzerie ecc. nel centro storico di Venezia:

- Casa.it – "Ristorazione" e "Bar, pub e caffè" a Venezia
- Immobiliare.it – licenze e attività in vendita
- Idealista – cessione attività a Venezia
- Subito.it – ricerche "bar", "ristorante", "cessione" nel Comune di Venezia

Vengono scartati gli annunci di Mestre, Marghera, terraferma e resto della provincia. Se un annuncio non indica la zona lo ricevi comunque con "❓ zona da verificare".
La prima volta ricevi l'elenco di tutto quello che è già online; da lì in poi solo le novità.

## Configurazione (circa 10 minuti)

### 1. Crea il bot Telegram
1. Su Telegram apri **@BotFather** e scrivi `/newbot`.
2. Scegli un nome (es. "Annunci Venezia") e uno username che finisca con `bot`.
3. BotFather ti dà un **token** tipo `123456789:AAH...`: copialo.
4. Apri la chat del tuo nuovo bot e premi **Avvia** (o scrivigli un messaggio qualsiasi).

### 2. Trova il tuo chat ID
Apri nel browser (sostituisci il token):
```
https://api.telegram.org/bot<TOKEN>/getUpdates
```
Cerca `"chat":{"id":123456789` — quel numero è il tuo **chat ID**.
(Se la pagina è vuota, scrivi ancora un messaggio al bot e ricarica.)

### 3. Crea il repository su GitHub
1. Crea un nuovo repository, anche **privato** (es. `venezia-annunci`).
2. Carica tutti i file di questa cartella, compresa la cartella `.github/workflows`.
   Dal sito: *Add file → Upload files* e trascina il contenuto della cartella.

### 4. Aggiungi i segreti
Nel repository: **Settings → Secrets and variables → Actions → New repository secret**
- `TELEGRAM_BOT_TOKEN` = il token del punto 1
- `TELEGRAM_CHAT_ID` = il numero del punto 2

### 5. Prova subito
Scheda **Actions → "Annunci bar e ristoranti Venezia" → Run workflow**.
Dopo circa un minuto dovresti ricevere il primo messaggio su Telegram.

## Personalizzare
Tutto è in cima a `monitor.py`:
- `INCLUDI_ISOLE_MINORI = True` per includere Lido, Murano, Burano ecc.
- `ZONE_ISOLA`, `ESCLUSE`, `TIPO_LOCALE`: parole chiave per zona e tipo di locale.
- `SOURCES`: aggiungi o togli pagine da controllare.
- Frequenza: riga `cron` in `.github/workflows/monitor.yml` (`7 */2 * * *` = ogni 2 ore; `7 * * * *` = ogni ora).
- GitHub a volte avvia i controlli programmati con qualche minuto di ritardo: è normale.

Per ricevere di nuovo tutto da capo, cancella `seen.json` dal repository.

## Da sapere
- Alcuni siti (soprattutto Idealista e a volte Immobiliare.it) bloccano gli accessi automatici dai server di GitHub. Se succede, quella fonte viene saltata e le altre continuano a funzionare; se **tutte** falliscono ricevi un avviso su Telegram (al massimo uno al giorno). Puoi vedere il dettaglio di ogni giro nella scheda Actions.
- Se un sito cambia la struttura delle pagine, la fonte può smettere di restituire annunci: nel log della scheda Actions compare "0 annunci letti".
- Il workflow fa un piccolo commit al giorno su `seen.json`: serve anche a evitare che GitHub sospenda le azioni programmate dopo 60 giorni di inattività.
