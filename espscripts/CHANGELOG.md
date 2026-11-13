# 0.3.0

- Importér boards, sensorer og udvidelsesboards fra et offentligt produktlink.
- Forhåndsvis og ret navn, hardwaretype, familie/tilslutning, beskrivelse og dokumentationslink før gemning.
- Find eksisterende katalogmodeller og genbrug kendte ESPHome-metadata uden at gætte på board-ID.
- Udvidelsesboards kan bruges som moduler ved siden af et separat ESP32-board og findes i sensorvælgeren.
- Beskrivelser, hardwaretype og ESPHome-metadata bevares ved redigering og i backup.
- Linkhentning med HTTPS, validering af netværksadresser, TLS og begrænsninger på størrelse, dybde og svartid.
- Afprøvet med Seeed Studio mmWave for XIAO og XIAO ESP32C3.
- Eksisterende data og import af backupformat 1 og 2 er fortsat understøttet.

# 0.2.0

- Nyt grafisk layout med hardwarekort, biblioteksoverblik og et guidet oprettelsesforløb i tre trin.
- Indbygget katalog med 211 boards og 200 ESPHome-sensorkomponenter samt søgning og kategorifiltre.
- Tilføj og redigér egne boards og sensorer, og vælg dem i opsætninger.
- Standardprint med COMMON, base.yaml, wireguard.yaml, secrets, ESP-IDF og logger. Generator til enhedsnavn, secret-prefix, chipvariant og flashstørrelse.
- Egne standardprint med versionshistorik, som kan genbruges til nye enheder.
- Eget appikon og logo til HA-appbutikken.
- Backupformat 2 med egne katalogposter; import af format 1 er fortsat understøttet. Eksisterende opsætninger bevares.

# 0.1.0

Første udgave: ESPHome YAML-bibliotek, søgning og filtre, sensorblokke og komplette opsætninger, ledningsføring, teststatus, revisionshistorik, kopiering, YAML-import/-eksport og JSON-backup med historik.
