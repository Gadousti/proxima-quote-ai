#!/bin/bash
cd "$(dirname "$0")"

echo "========================================"
echo " Installation de Proxima Quote AI"
echo "========================================"
echo

# Try python3
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 n'est pas installé."
  echo "Installe Python depuis https://www.python.org/downloads/macos/"
  echo "puis relance ce fichier."
  echo
  read -p "Appuie sur Entrée pour fermer..."
  exit 1
fi

echo "Python détecté :"
python3 --version
echo

echo "Création de l'environnement virtuel..."
python3 -m venv .venv
if [ $? -ne 0 ]; then
  echo "Échec de création de l'environnement virtuel."
  read -p "Appuie sur Entrée pour fermer..."
  exit 1
fi

source .venv/bin/activate

echo
echo "Mise à jour de pip..."
python -m pip install --upgrade pip

echo
echo "Installation des dépendances..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
  echo
  echo "L'installation a échoué."
  read -p "Appuie sur Entrée pour fermer..."
  exit 1
fi

echo
echo "========================================"
echo " Installation terminée avec succès."
echo " Tu peux maintenant ouvrir LANCER_MAC.command"
echo "========================================"
echo
read -p "Appuie sur Entrée pour fermer..."
