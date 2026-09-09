# Provenance — prueba de fecha del commit inicial

[`first-commit.txt`](first-commit.txt) contiene el hash del primer commit del
repo (`5ec0a758d4f93be1d834211b51954cc3dd516b71`, 2026-08-22). Ese archivo está
estampado con [OpenTimestamps](https://opentimestamps.org/): el hash SHA256 del
archivo quedó anclado en la blockchain de Bitcoin, lo que da una prueba
verificable por cualquiera (no solo por GitHub) de que ese commit ya existía en
esa fecha — sin necesidad de confiar en un tercero.

## Estado actual: **confirmado**

El sello quedó anclado en el bloque de Bitcoin **966222**
(`ots upgrade` → "Success! Timestamp complete"). Es una prueba completa,
verificable por cualquiera para siempre — no depende de que GitHub, este repo,
ni ningún calendar server de OpenTimestamps sigan existiendo.

## Cómo verificar (cualquiera, en cualquier momento)

```bash
pip install opentimestamps-client
ots verify docs/provenance/first-commit.txt.ots
```

Confirma que el contenido de `first-commit.txt` (el hash de commit) existía en
esa fecha. Necesita un nodo de Bitcoin propio para chequear el header del
bloque de forma totalmente independiente (`--bitcoin-node <url>`); sin uno, el
verificador web de [opentimestamps.org](https://opentimestamps.org/) hace el
mismo chequeo contra block explorers públicos.

## Qué prueba esto y qué no

Prueba que **ese hash de commit exacto existía en esa fecha** — el commit en sí
ya encapsula el árbol de archivos completo del scaffold inicial en ese momento.
No es un registro legal de autoría ni un derecho de propiedad intelectual — es
evidencia técnica objetiva de fecha, útil como respaldo si alguna vez hace
falta demostrar cuándo empezó este proyecto.
