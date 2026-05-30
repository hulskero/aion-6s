# AION-6S: AI Operating Layer for Jailbroken iPhone 6s

Minimal AI agent framework pro jailbreakly iPhone (2GB RAM) s a-Shell/NewTerm.

## Použití

```bash
# Setup
pip install -r requirements.txt
export NVIDIA_API_KEY="nvapi-xxx"  # nebo vlož do config.json

# Run
python aion.py
```

## Režimy

- `/plan` - AI plní, nic nevykonává
- `/build` - krok za krokem s potvrzením  
- `/auto` - plně autonomní, guardrails blokují ničení
- `/chat` - normální chat (výchozí)

## Bezpečnost

- Blokovány nebezpečné příkazy (rm -rf /, dd, reboot, sudo...)
- Destructive operace vyžadují potvrzení
- Audit log všech operací
- API key měl být v env var (ne v config.json)

## Pluginy

```
@plugin battery      - stav baterie
@plugin location     - GPS poloha  
@plugin system_tools - systémové info
```

## Requirements

- Python 3.10+ (funguje i na iOS Python 2.x port)
- NVIDIA API key (DeepSeek model)
- Jailbroken iPhone s a-Shell nebo NewTerm

## License

MIT - užij si na vlastní riziko.