# Reporte de la Fase 0 (M0.1 a M0.5)

Estado: **M0.1–M0.5 validados.** M0.5 se completó con 3 máquinas reales del
usuario en vez de VMs cloud (Mac M4 + PC Intel i7/Ubuntu + ASUS ROG Ally X con
Windows/WSL2), todas en la misma LAN. M0.6 (modelo grande en GPU real) sigue
pendiente. No hay recomendación go/no-go final para Fase 1 hasta tener M0.6.

## M0.1 — Spike de entorno

La imagen `enjambre/swarm-node:dev` (Python 3.10 + torch CPU + hivemind + petals)
builda y corre en Docker Desktop sobre Apple Silicon (arm64 nativo, sin emulación).
Se encontraron y corrigieron 4 bugs reales de dependencias en el camino — ver el
historial de commits (`Corregir Dockerfile de swarm-node para que el build M0.1
funcione`) para el detalle de cada uno: `pip --index-url` vs `--extra-index-url`,
`pkg_resources` faltante en setuptools recientes, `grpc_tools` faltante al
desactivar build isolation, y la necesidad de instalar el commit exacto de
`hivemind` que `petals` pinea (no el HEAD de `main`, que ya no expone
`hivemind.PeerID`).

## M0.2 — Smoke test de un solo nodo

Un nodo (`single-node`, ancla su propio swarm con `--new_swarm --num_blocks 24`)
sirve los 24 bloques de `bigscience/bloom-560m`. El cliente se conecta vía DHT y
genera texto coherente end-to-end. Bugs corregidos: el CLI de petals espera el
modelo como argumento posicional (no `--model`); petals no tiene modo "solo DHT
sin bloques" (el nodo `--new_swarm` siempre hostea bloques él mismo, y en CPU
exige `--num_blocks` explícito).

## M0.3 — Partición en 3 nodos (localhost)

`node-1` (bloques 0-8, ancla el DHT) + `node-2` (8-16) + `node-3` (16-24), todos
en el mismo host vía `docker-compose`. Los tres anuncian sus rangos correctamente
y el swarm cubre el modelo completo (0-24). Bug corregido: `get-bootstrap-peer.sh`
usaba la IP que hivemind imprime para sí mismo (no ruteable entre contenedores)
en vez del nombre DNS del servicio de compose.

Este test corre en localhost — **no ejercita el NAT traversal real de hivemind**
(eso es M0.5). Mide solo el overhead puro del mecanismo de partición/pipeline.

## M0.4 — Harness de corrección

`benchmarks/correctness_check.py` comparó los logits de `bloom-560m` corrido (a)
localmente en `transformers` plano vs (b) distribuido a través de los 3 nodos de
M0.3:

```
similaridad coseno = 1.000012
norma relativa     = 0.000167
```

Prácticamente idéntico (la diferencia es ruido de punto flotante entre pasadas,
no error de partición) — muy por encima del umbral fijado (`cos_sim > 0.999`).
Confirma que partir el modelo en 3 procesos separados no degrada la salida.
Bug corregido: la imagen Docker no incluye el código del repo (el Dockerfile solo
instala dependencias) — se agregó un bind mount de `benchmarks/` al servicio
`client` en vez de rebuildear la imagen por cada cambio al script.

## M0.5 — Máquinas reales separadas ✅

Se hizo con 3 máquinas reales del usuario en la misma LAN, en vez de VMs cloud:

| Nodo | Hardware | SO | Bloques |
|---|---|---|---|
| Ancla | MacBook Pro M4, 16GB | macOS (Docker Desktop) | 0-8 |
| Follower | Intel i7, 16GB, RX 5700 XT (sin usar, CPU only) | Ubuntu | 8-16 |
| Follower | ASUS ROG Ally X (Ryzen Z1 Extreme) | Windows 11 + WSL2 | 16-24 |

**Resultado**: inferencia distribuida real, atravesando las tres máquinas.

```
Route found: 0:8 via …bWzPbW => 8:16 via …qU4eAh => 16:24 via …u1nRFL
RESULTADO: Hola, como estas? Yo estoy en el mismo dilema que tu, y no sé si me
```

### Bugs reales encontrados y corregidos en el camino

Ninguno de estos aparecía en las pruebas de localhost (M0.1-M0.4) — todos
salieron solo al usar máquinas, sistemas operativos y redes de verdad:

1. **bash 3.2 (macOS)**: `"${ARR[@]}"` sobre un array vacío tira "unbound variable" bajo `set -u`. Funciona en cualquier bash 4.4+ de Linux; rompe en Mac.
2. **Follower sin puerto publicado**: el branch de follower de `run-remote-node.sh` no hacía `-p` ni fijaba `--host_maddrs` — ningún peer podía alcanzarlo.
3. **Auto-anuncio de IP interna de Docker**: sin `SELF_IP` explícito, hivemind anunciaba `172.17.0.2` (la IP del contenedor), no ruteable desde otra máquina.
4. **Bloques duplicados**: con `--num_blocks` (auto-balance) y nodos que no se ven bien entre sí, dos nodos eligieron el mismo rango (8-15) y nadie cubrió 0-7. Se agregó `BLOCK_INDICES` para asignación explícita.
5. **Firewall de Windows (puerto 31337)**: bloqueaba el puerto del swarm. El firewall no es parte de WSL2 — hay que abrirlo en Windows aunque uses "mirrored networking".
6. **UFW sin regla para 31337** en la Ubuntu (aunque Docker suele saltear UFW igual al publicar puertos).
7. **`routing: not found` — el más sutil**: pasarle al cliente solo la dirección del ancla no alcanza. El DHT le da el *peer ID* del nodo que sirve cada rango, pero no su *dirección*; el cliente cae a resolverla por DHT `FindPeer`, que en un swarm de 3 nodos no tiene red suficiente y falla. **Hay que pasarle al cliente las direcciones de todos los nodos.** En el swarm público de petals esto no se nota porque el cliente termina conectado a muchos servidores igual.

### Limitación de esta corrida

Las tres máquinas están en la **misma LAN**, así que esto todavía **no ejercita
el NAT traversal real de hivemind** entre redes distintas (el objetivo original
de M0.5). Para eso falta un nodo genuinamente fuera de la red — una VM cloud o
la casa de alguien más. Lo que sí quedó validado: máquinas físicas distintas,
tres sistemas operativos distintos, y red real (no localhost).

## M0.6 (parcial) — Modelo de programación real ✅

Se probó `deepseek-ai/deepseek-coder-1.3b-instruct` (arquitectura Llama, 24
capas) repartido 8/8/8 entre las mismas tres máquinas. Generó código Python
correcto y con el estilo de docstring esperado de un modelo instruct.

### Bug real: `rope_scaling` con formato viejo

`transformers==4.43.1` (pineado por petals) tiene una regresión: sus
funciones `_validate_*` de RoPE leen `rope_scaling["rope_type"]` directo y
exigen esa clave en `required_keys`, pero varios modelos Llama (deepseek-coder
1.3b y 6.7b entre otros) usan el formato viejo `{"type": "linear"}` en vez de
`{"rope_type": "linear"}`. `rope_config_validation()` sí tolera ambos
formatos para su propia lectura, pero no propaga la normalización a las
funciones que llama después → `KeyError`. Parchado en el Dockerfile
normalizando el dict una sola vez, apenas se entra a esa validación.

### Bug real (más sutil): reiniciar a mitad de una descarga dejó el DHT inconsistente

Con un archivo de pesos de 2.5GB y la conexión de la Ubuntu bajando a
~700KB/s (~55 min para el archivo completo), el contenedor se reinició antes
de terminar de descargar. El proceso de `petals` **anuncia que se une al DHT
antes de terminar de cargar los pesos** — quedó "Announced" pero nunca
"Started" ni "Loaded block N". Dejar que la descarga terminara en background
no alcanzó: el nodo necesitó un **reinicio limpio adicional** (ahora con los
pesos ya en caché, casi instantáneo) para que el anuncio del DHT quedara
consistente y el resto del swarm pudiera encontrarlo. Sin ese segundo
reinicio, la generación fallaba con `MissingBlocksError` indefinidamente
pese a que el nodo ya estaba sano y "Started".

**Para próxima vez**: no confiar en que un nodo cuya descarga se interrumpió
vaya a auto-recuperarse solo con solo esperar — reiniciarlo una vez que los
pesos estén confirmados en caché.

## M0.6 — por qué el 6.7B entraba en loop de reinicio (resuelto)

Al escalar de 1.3B a `deepseek-coder-6.7b-instruct`, el Mac y la Ubuntu
entraban en un bucle: arrancaban, anunciaban sus bloques al DHT, y morían
~30 segundos después. Sin traceback, sin mensaje de error, `ExitCode=0` y
`OOMKilled=false`. Parecía un problema del modelo grande. No lo era, y las
tres pistas juntas explican por qué costó tanto verlo.

### La causa: OOM global de la VM, no del contenedor

La evidencia estaba en el log del kernel de la VM de Docker, no en los logs
de Docker:

```
hf-xet-7 invoked oom-killer: gfp_mask=0x140cca, order=0, oom_score_adj=0
oom-kill:constraint=CONSTRAINT_NONE,...,global_oom,task=python,pid=25706
Out of memory: Killed process 25706 (python) total-vm:6541524kB anon-rss:1519700kB
```

`constraint=CONSTRAINT_NONE` + `global_oom` es la clave: el que se quedó sin
memoria fue **el kernel de la VM entera**, no el cgroup del contenedor.
`docker inspect` solo reporta `OOMKilled=true` cuando mata el cgroup — por eso
decía `false`, y por eso el exit code era 0: petals vio morir a su hijo y
cerró ordenadamente. Todo lo que Docker mostraba decía "salió solo, sin error".

Se llegó ahí con:

```bash
docker run --rm --privileged --pid=host alpine \
  sh -c "dmesg | grep -iE 'out of memory|oom.kill'"
```

**Para la próxima**: ante un contenedor que muere con `ExitCode=0` y sin
traceback, mirar `dmesg` del host antes que nada. `OOMKilled=false` NO
descarta un OOM.

### Por qué se quedó sin memoria: sesiones de chat abandonadas

`chat.sh` corría con `docker run --rm -it`. `--rm` solo borra el contenedor
cuando el proceso **termina** — al cerrar la terminal sin salir del REPL, el
contenedor queda vivo, bloqueado en `input()`, con el modelo y el cliente en
RAM. Como tampoco tenía `--name`, cada chat creaba uno nuevo con nombre
aleatorio y se apilaban invisibles:

```
magical_yonath        917.8MiB    Up 32 minutes    "python3 -u chat.py"
xenodochial_austin    913.2MiB    Up 47 minutes    "python3 -u chat.py"
wizardly_bose         1.527GiB    Up 50 minutes    "python3 -u chat.py"
fervent_mcclintock    1.489GiB    Up 2 hours       "python3 -u chat.py"
flamboyant_meninsky   752.6MiB    Up 3 hours       "python3 -c ..."
```

**5.6 GB de los 7.6 GB de la VM**, ocupados por sesiones muertas. Al
limpiarlas, la memoria disponible pasó de 1.27 GB a 6.6 GB y el nodo arrancó
a la primera. Confirmación de que no tenía nada que ver con el modelo: el
**1.3B también estaba en loop** (`RestartCount=15`) con la misma firma exacta.

### El gatillo: `hf_xet` bajando un shard de 10 GB

Quien invocó al OOM killer fue `hf-xet`, el descargador nuevo de HuggingFace
(activo por defecto desde `huggingface_hub` 0.30), que baja en chunks
paralelos y los bufferea en RAM. `deepseek-coder-6.7b-instruct` tiene un
shard de **9.98 GB** en un solo archivo — bufferearlo en una VM de 7.6 GB ya
saturada no tenía salida. `HF_HUB_DISABLE_XET=1` vuelve al descargador
clásico, que escribe a disco en streaming con memoria constante.

### Lo que convertía un crash en un bucle infinito

El nodo **no montaba ningún volumen para el cache de HuggingFace** — solo
`/root/.hivemind` para la identidad. El cache vivía en la capa de escritura
del contenedor. Con `--restart unless-stopped`, el ciclo era: arranca →
descarga 10 GB → OOM → reinicia → **descarga los 10 GB otra vez** → OOM, para
siempre. Nunca iba a converger solo.

Esto también explica retroactivamente el bug de "reiniciar a mitad de la
descarga dejó el DHT inconsistente" documentado más arriba: no era el DHT, era
que cada reinicio empezaba la descarga de cero.

### Correcciones aplicadas

| Dónde | Qué |
|---|---|
| `run-remote-node.sh` | Monta `enjambre-hf-cache` — el cache sobrevive a reinicios |
| `run-remote-node.sh` | `HF_HUB_DISABLE_XET=1` — descarga con memoria constante |
| `run-remote-node.sh` | `MEM_LIMIT` opcional → el OOM queda atribuido al cgroup y `OOMKilled=true` lo delata |
| `chat.sh` | `--name enjambre-chat` + limpieza de la sesión previa — no se apilan más |
| `chat.sh` | `--memory 2g` — una sesión colgada no puede voltear el nodo |

Los tres nodos quedaron en `RestartCount=0` y `Started`. El throughput del
Mac subió de 620 a 2733 tokens/seg por bloque en forward pass, simplemente
por tener memoria libre.

### Techo de recursos real (por qué el 6.7B todavía no entra)

Con el bug resuelto, el límite que queda es de recursos, y es medible. Lo
llamativo: **no es falta de hardware, son los hypervisors dando la mitad**.

| Máquina | RAM física | RAM que ve el nodo | Disco libre |
|---|---|---|---|
| Mac M4 | 16 GB | **7.7 GB** (VM de Docker Desktop) | 405 GB |
| ASUS ROG Ally X | 24 GB | **7.6 GB** (WSL2) | 947 GB |
| Intel i7 / Ubuntu | 15.5 GB | 15.5 GB (nativo) | **14 GB** |

El 6.7B en bfloat16 son 0.40 GB por bloque × 32 bloques = **13 GB de pesos**,
más ~1.5 GB de runtime por nodo. Contra ~19 GB disponibles hoy, queda sin
margen — y el usuario pidió explícitamente no llevarlo al máximo. Además la
Ubuntu tiene 14 GB de disco libre y el shard más grande pesa 9.98 GB (el repo
completo son 27 GB porque publica `.safetensors` y `.bin` duplicados).

Para que el 6.7B entre con holgura, sin comprar nada:

1. **Mac**: subir la RAM de la VM en Docker Desktop (Settings → Resources) de 7.7 a ~12 GB.
2. **ASUS**: crear `C:\Users\<usuario>\.wslconfig` con `[wsl2]` / `memory=16GB` y `wsl --shutdown`.
3. **Ubuntu**: liberar disco (`docker system prune -a` recupera ~2.8 GB de build cache) o apuntar el cache de HF a otra partición.

## Qué modelos podemos correr (y GPT-OSS)

`petals` **no** sirve cualquier modelo de HuggingFace: tiene una
implementación distribuida escrita a mano por arquitectura, y solo hay cuatro
(`petals/models/`): **bloom, llama, falcon, mixtral**. El `model_type` del
`config.json` tiene que ser uno de esos — no alcanza con que el modelo sea
"parecido a Llama".

Se evaluó **GPT-OSS** (que ya corre bien en la ASUS vía Ollama) y queda
descartado para el swarm:

| Modelo | `architectures` | `model_type` | ¿Sirve? |
|---|---|---|---|
| `openai/gpt-oss-20b` | `GptOssForCausalLM` | `gpt_oss` | ❌ |
| `openai/gpt-oss-120b` | `GptOssForCausalLM` | `gpt_oss` | ❌ |
| `deepseek-ai/deepseek-coder-*-instruct` | `LlamaForCausalLM` | `llama` | ✅ |

Soportarlo significaría escribir `petals/models/gpt_oss/` (bloque, config y
modelo distribuido) — es trabajo de Fase 1+, no un cambio de parámetro. Que
GPT-OSS ande bien en la ASUS con Ollama no es contradictorio: Ollama corre el
modelo **entero en una máquina**, que es justo lo que Enjambre no hace.

Chequeo rápido antes de proponer cualquier modelo:

```bash
curl -s https://huggingface.co/<org>/<modelo>/raw/main/config.json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['model_type'])"
```

## Pendiente

- **M0.5b** — repetir con al menos un nodo fuera de la LAN (VM cloud o casa de un amigo) para ejercitar NAT traversal de verdad.
- **M0.6 (completo)** — repetir con 6.7B después de subir la RAM de la VM del Mac y de WSL2 en la ASUS (ver "Techo de recursos real"). El bug que lo bloqueaba está resuelto; lo que falta es capacidad.
- **M0.7** — recomendación go/no-go para Fase 1, con los hallazgos de M0.5b/M0.6.
