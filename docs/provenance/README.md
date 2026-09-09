# Provenance — prueba de fecha del commit inicial

[`first-commit.txt`](first-commit.txt) contiene el hash del primer commit del
repo (`5ec0a758d4f93be1d834211b51954cc3dd516b71`, 2026-08-22). Ese archivo está
estampado con [OpenTimestamps](https://opentimestamps.org/): el hash SHA256 del
archivo quedó anclado en la blockchain de Bitcoin, lo que da una prueba
verificable por cualquiera (no solo por GitHub) de que ese commit ya existía en
esa fecha — sin necesidad de confiar en un tercero.

## Estado actual

El sello (`first-commit.txt.ots`) está **enviado, pendiente de confirmación**
en la blockchain de Bitcoin — el paso de anclado final (`upgrade`) tarda desde
minutos hasta algunas horas/un día, según cuándo los calendar servers de
OpenTimestamps agrupen este sello en un bloque confirmado.

## Cómo finalizarlo (más adelante)

```bash
pip install opentimestamps-client
ots upgrade docs/provenance/first-commit.txt.ots
```

Esto actualiza el `.ots` in-place con la prueba completa una vez confirmada.
Después hay que commitear el archivo actualizado.

## Cómo verificar (cualquiera, en cualquier momento)

```bash
pip install opentimestamps-client
ots verify docs/provenance/first-commit.txt.ots
```

Confirma que el contenido de `first-commit.txt` (el hash de commit) existía en
la fecha probada — independientemente de si GitHub sigue existiendo o de si
alguien pudiera alterar metadata ahí.

## Qué prueba esto y qué no

Prueba que **ese hash de commit exacto existía en esa fecha** — el commit en sí
ya encapsula el árbol de archivos completo del scaffold inicial en ese momento.
No es un registro legal de autoría ni un derecho de propiedad intelectual — es
evidencia técnica objetiva de fecha, útil como respaldo si alguna vez hace
falta demostrar cuándo empezó este proyecto.
