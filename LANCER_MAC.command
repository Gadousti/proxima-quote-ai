#!/bin/bash
cd "$(dirname "$0")"

echo "========================================"
echo " Lancement de Proxima Quote AI"
echo "========================================"
echo

if [ ! -d ".venv" ]; then
  echo "L'application n'est pas encore installée."
  echo "Ouvre d'abord INSTALLER_MAC.command."
  echo
  read -p "Appuie sur Entrée pour fermer..."
  exit 1
fi

source .venv/bin/activate

echo "Ouverture de l'application..."
streamlit run app.py
