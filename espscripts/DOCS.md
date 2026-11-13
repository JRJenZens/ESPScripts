# ESPScripts

Et dansk bibliotek i Home Assistant til ESPHome YAML: find og genbrug sensorblokke og komplette ESP32-opsætninger med tilslutninger, testnoter og versionshistorik.

## Installation i Home Assistant

Kræver Home Assistant OS eller en installation med Supervisor. Understøtter amd64 og aarch64.

1. Åbn **Indstillinger → Apps → Appbutik** (på ældre HA-versioner hedder det Tilføjelser).
2. Åbn menuen **⋮ → Repositories**, og tilføj:

   `https://github.com/JRJenZens/ESPScripts`

3. Opdatér appbutikken, find **ESPScripts**, og vælg **Installér**. Første installation bygger containeren og kan tage nogle minutter.
4. Start appen, slå **Vis i sidepanelet** til, og vælg **Åbn webbrugerflade**.

[Åbn tilføjelse af repository i Home Assistant](https://my.home-assistant.io/redirect/supervisor_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FJRJenZens%2FESPScripts)

Appen bruger Home Assistants Ingress og login. Ingen separat port eller adgangskode skal konfigureres. Biblioteket er fælles for HA-administratorer med adgang til appen; det har ikke separate brugerbiblioteker.

## Funktioner

- Opret og redigér komplette opsætninger og genbrugelige sensorblokke.
- Søg i navn, board, sensorer, tags, GPIO/tilslutninger, noter og YAML.
- Filtrér efter board, sensor, type og teststatus.
- Notér testet hardware/dato og ESPHome-version.
- Importér en `.yaml`/`.yml`-fil, kopiér kode, eller download YAML.
- Hver gemning opretter en revision med både kode og metadata.
- Se tidligere revisioner, og indlæs dem i editoren. Gem for at gendanne som en **ny** version; eksisterende historik bevares.
- Gem som kopi opretter en ny opsætning med status **Ikke testet**.
- Eksportér hele biblioteket inklusive historik som JSON-backup. Import opretter nye kopier og bevarer historik og versionsdatoer; den overskriver aldrig eksisterende opsætninger.
- Samtidige ændringer kontrolleres, så en gammel editor ikke overskriver en nyere version.

## Arbejdsgang

Start med **Importér YAML** fra en konfiguration, du allerede har. Angiv board, sensorer og ledningsføring, og vælg om koden er en sensorblok eller en komplet opsætning. Angiv **Testet** først efter en fysisk test, og skriv hardware og dato i testfeltet.

Når du genbruger en opsætning, vælg **Gem som kopi**, tilpas navn, GPIO og øvrige værdier, og kopiér eller hent YAML til ESPHome Device Builder. En sensorblok kan indsættes i din konfiguration eller gemmes som en ESPHome-pakkefil. Biblioteket sammensætter ikke automatisk flere YAML-blokke.

**Syntakskontrol er ikke ESPHome-validering.** ESPScripts kontrollerer, at YAML kan læses som en mapping, og understøtter ESPHome-tags som `!secret`, `!include` og `!lambda`. Koden køres ikke. Board-understøttelse, komponenter, GPIO-konflikter og elektriske forhold skal kontrolleres i ESPHome og på hardwaren. YAML-ankre og aliaser understøttes ikke i version 0.1.

## Data og backup

SQLite-databasen gemmes i appens vedvarende `/data/espscripts.sqlite3` og indgår i en HA-backup, **når ESPScripts er valgt med i backupen**. Tag desuden JSON-backup fra biblioteket før større ændringer. JSON-import har en grænse på 32 MiB; YAML-import 500 kB. Biblioteket er tomt ved første start.

Brug `!secret`-referencer; gem ikke `secrets.yaml`, rigtige Wi-Fi-adgangskoder eller API-nøgler i biblioteket. JSON-backup indeholder hele bibliotekets indhold og skal opbevares derefter. Der er ingen cloudsynkronisering eller upload af biblioteket til GitHub. GitHub indeholder kun appens kildekode.

## Manuel installation

Pak ZIP-filen ud. Kopiér mappen `espscripts` (den med `config.yaml` og `Dockerfile`) til `/addons/espscripts` på HA via en adgang, der kan skrive i den lokale apps-mappe. Genindlæs appbutikken, og installér ESPScripts under **Lokale apps**. En ZIP uploades ikke direkte til HACS eller appbutikken. GitHub-repository-metoden ovenfor er normalt nemmest.

## Lokal udvikling

```sh
python3 -m venv .venv
.venv/bin/pip install -r espscripts/requirements.txt
.venv/bin/python -m unittest discover -s tests -v
ESPSCRIPTS_LOCAL=1 ESPSCRIPTS_DB=./library.sqlite3 .venv/bin/python espscripts/app.py
```

Åbn `http://127.0.0.1:8099`. `ESPSCRIPTS_LOCAL=1` er kun til lokal udvikling: produktionsappen tillader kun Ingress-proxyen på `172.30.32.2`, og appens konfiguration eksponerer ingen værtsport.

De lokale tests dækker lagring, versionshistorik, backup, YAML-kontrol, adgangskontrol og samtidige ændringer. Browserkontrol dækker oprettelse, genåbning, søgning og historik. Docker er ikke tilgængelig i udviklingsmiljøet, så containerbygning, installation og Ingress skal afprøves på en rigtig HA-installation. GitHub-workflows er ikke aktiveret i denne udgave.

## Dokumentation

- [Home Assistant: Ingress](https://contributors.home-assistant.io/apps/guides/ingress/)
- [Home Assistant: appkonfiguration](https://contributors.home-assistant.io/apps/reference/configuration/)

Licens: MIT.
