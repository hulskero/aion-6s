# AION-6S: AI Operating Layer for Jailbroken iPhone 6s

Minimal AI agent framework pro jailbreakly iPhone (2GB RAM) s a-Shell/NewTerm.
Pouze Python stdlib — není potřeba pip ani git.

## Instalace na iPhone (a-Shell)

```bash
# 1. Stáhni bootstrap
curl -sL https://raw.githubusercontent.com/hulskero/aion-6s/main/bootstrap.py -o bootstrap.py

# 2. Spusť bootstrap (stáhne všech 17 souborů do složky aion-6s/)
python3 bootstrap.py

# 3. Vstup do složky
cd aion-6s

# 4. Nastav API klíč (doporučeno)
export NVIDIA_API_KEY="nvapi-..."

# 5. Spusť AION
python3 aion.py
```

Pokud nemáš API klíč, AION tě vyzve k zadání při prvním spuštění a uloží ho do `config.json`.

## Aktualizace na iPhonu

Uvnitř AION napiš `/update` — stáhne nejnovější soubory z GitHubu a ukončí se.
Pak spusť znovu: `python3 aion.py`

## Režimy

- `/plan` — AI plánuje, nic nevykonává
- `/build` — krok za krokem s potvrzením
- `/auto` — plně autonomní, guardrails blokují ničení
- `/chat` — normální chat (výchozí)

## Příkazy

| Příkaz | Význam |
|--------|--------|
| `/retry` | Zopakuje poslední dotaz (po API chybě) |
| `/clear` | Resetuje konverzaci |
| `/plugins` | Seznam pluginů |
| `/status` | Info o session |
| `/save jmeno` | Uložit session |
| `/load jmeno` | Nahrát session |
| `/update` | Stáhnout nejnovější verzi |
| `/help` | Všechny příkazy |

## Pluginy

```
@plugin battery          - stav baterie
@plugin location         - GPS poloha přes IP
@plugin system_tools     - CPU, disk, uptime, WiFi
@plugin webfetch <url>   - stáhne obsah stránky
@plugin weather <město>  - počasí (wttr.in + Open-Meteo fallback)
```
> **Poznámka:** Pluginy `nfc_manager` a `daemon` byly odstraněny v rámci Phase 1 cleanup.

## Bezpečnost

- Blokovány nebezpečné příkazy (rm -rf, dd, reboot, sudo...) prostřednictvím rozšířených guardrails
- Destruktivní operace vyžadují potvrzení (kromě `/auto`)
- Audit log všech operací s obfuskací tajných dat
- API klíč ideálně v `NVIDIA_API_KEY` env var (ne v `config.json`)
- Vstupní validace a sanitizace pro prevenci injection útoků
- Velikostní omezení výstupu s automatickým zkrácením
- Ochrana proti shell injection přes bezpečné subprocess volání

## Požadavky

- Jailbreaknutý iPhone s a-Shell nebo NewTerm
- Python 3.10+ (dostupný v a-Shell)
- NVIDIA API klíč (zdarma na build.nvidia.com)
- 2 GB RAM stačí

## License

MIT

## Nedávná vylepšení (2026-05-31)

- Rozšířené bezpečnostní guardrails s komplexnější detekcí destruktivních příkazů
- Vstupní validace a sanitizační funkce v `core/input_validator.py`
- Preference proměnné prostředí `NVIDIA_API_KEY` před ukládáním do `config.json`
- Obfuskace tajných dat v audit logu a výstupech
- Jednotkové testy pro validaci a guardrails v `tests/` adresáři
- Vylepšená zpětná vazba s barevnými indikátory a časováním
- `/retry` příkaz pro automatické opakování selhaných API dotazů
- Konzervativnější výchozí hodnoty optimalizované pro iPhone 6s (max_tokens=512, request_timeout=300s)