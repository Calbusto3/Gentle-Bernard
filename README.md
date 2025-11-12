# Gentle Bernard Bot

Un bot Discord privé, basé sur `discord.py` 2.x.

## Prérequis
- Python 3.10+
- Permissions activées dans le portail Discord Developer (Message Content Intent)
- Un token de bot stocké dans un fichier `.env` que vous créez

## Installation
```bash
# 1) Créer l'environnement virtuel (recommandé)
python -m venv venv

# 2) Activer l'environnement (Windows PowerShell)
./venv/Scripts/Activate.ps1

# 3) Installer les dépendances
pip install -r requirements.txt
```

## Configuration
Créez un fichier `.env` à la racine du projet avec :
```
TOKEN_BOT=VOTRE_TOKEN_ICI
# Optionnel
PREFIX=!
# Optionnel: IDs de guildes pour sync rapide des slash commands (séparés par des virgules)
GUILD_IDS=
```

- Activez l'intent "Message Content" dans le portail Discord pour le bot.

## Lancement
```bash
python main.py
```

Le bot charge automatiquement tous les cogs dans le dossier `cogs/` et synchronise les commandes slash.

## Commandes incluses
- voir help

## Structure du projet
```
CIGaming bot/
├─ cogs/
│  ├─ __init__.py
│  └─ basic.py
│  └─ autre...
├─ utils/
│  ├─ __init__.py
│  ├─ config.py
│  └─ logging_setup.py
│  └─ autre...
├─ requirements.txt
├─ .gitignore
└─ README.md
```

## Notes
- c'est un bot privé reservé à un serveur précis.