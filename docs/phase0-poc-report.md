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
| `run-remote-node.sh` | Monta `enjambre-petals-cache` **y** `enjambre-hf-cache` — los pesos sobreviven a reinicios |
| `run-remote-node.sh` | `HF_HUB_DISABLE_XET=1` — descarga con memoria constante |
| `run-remote-node.sh` | `MEM_LIMIT` opcional → el OOM queda atribuido al cgroup y `OOMKilled=true` lo delata |
| `chat.sh` | `--name enjambre-chat` + limpieza de la sesión previa — no se apilan más |
| `chat.sh` | `--memory 2g` — una sesión colgada no puede voltear el nodo |

Los tres nodos quedaron en `RestartCount=0` y `Started`. El throughput del
Mac subió de 620 a 2733 tokens/seg por bloque en forward pass, simplemente
por tener memoria libre.

### Detalle que casi arruina el arreglo: el servidor no usa el cache de HF

Montar `~/.cache/huggingface` en el nodo **no alcanza**. El servidor de petals
usa su propio directorio (`PETALS_CACHE`, o `~/.cache/petals` por defecto —
`petals.utils.disk_cache.DEFAULT_CACHE_DIR`). Dentro del nodo:

```
2.6G    /root/.cache/petals        <- los pesos de los bloques viven aca
3.6G    /root/.cache/huggingface   <- esto lo usa el CLIENTE (chat.sh)
```

Con el volumen en el path equivocado, el arreglo parecía aplicado pero los
pesos seguían en la capa efímera del contenedor. Se montan los dos volúmenes.

En `~/.cache/petals` también vive `throughput_v5.json`, el resultado del
benchmark de arranque. Sin persistirlo, cada reinicio vuelve a medir: ~2
minutos por arranque, y en la Ubuntu el speedtest de red ni siquiera termina
dentro de su timeout de 60s (`Network throughput is not available: speedtest
did not finish in 60 seconds`), así que reporta un default de 100 Mbit/s que
no refleja nada.

### Confirmación: el 6.7B carga sin problemas con el arreglo aplicado

Tras subir la RAM de los hypervisors (Docker Desktop 7.7 → 9.7 GB, WSL2 7.6 →
11.7 GB) se redesplegó el mismo modelo que antes entraba en bucle:

| Nodo | Bloques | Resultado |
|---|---|---|
| Mac (ancla) | 0:11 | `Started`, `RestartCount=0`, `OOMKilled=false` |
| ASUS | 19:32 | `Started`, `RestartCount=0`, `OOMKilled=false` |

Los dos bajaron sus ~10 GB de pesos y cargaron todos sus bloques sin un solo
reinicio. El bug está cerrado: no era el modelo, era la memoria.

### Las estimaciones de memoria eran demasiado conservadoras (mmap)

Dato medido, contra-intuitivo: el Mac sirviendo **11 bloques del 6.7B** (4.5 GB
de pesos en teoría) consume **893 MB** de RSS.

```
MEM=893.6MiB / 8GiB
```

petals mapea los pesos desde disco con `mmap` en vez de copiarlos a memoria
anónima, así que el kernel los pagina bajo demanda y el consumo residente es
una fracción del tamaño del modelo. Bajo presión de memoria esas páginas se
descartan y se releen del disco — no van a swap.

Consecuencia práctica: **el número que importa para dimensionar un nodo no es
"GB de pesos" sino el disco disponible y el ancho de banda al disco.** Se le
pueden asignar bastantes más bloques a un nodo de los que sugiere el cálculo
de `params × bytes`. El cálculo teórico sigue sirviendo como cota superior
segura, pero deja mucha capacidad sin usar.

### Techo de recursos real (el cálculo conservador previo)

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

## Tres límites de contexto ocultos, encadenados (aider no arrancaba)

Al apuntar aider al gateway, la primera consulta moría del lado del servidor
sin que aider mostrara ningún error claro — solo `Waiting for...` colgado.
La causa: petals elige **tres** valores por defecto según el tipo de atención
del modelo (multi-query attention como Llama 2/Falcon vs. el resto), y
`deepseek-coder` (basado en Llama 1, sin GQA) cae en "el resto":

| Flag | Default con MQA | Default sin MQA (deepseek-coder) |
|---|---|---|
| `--inference_max_length` | 8192 | **2048** |
| `--attn_cache_tokens` | 16384 | **4096** |
| `--max_batch_size` | 8192 | **2048** |

2048 alcanza apenas para una consulta corta — el system prompt de aider más
el contexto del repo ya suman ~2600 tokens. Los tres fallan **en cadena**,
cada uno tapando al siguiente, así que se encontraron uno por uno subiendo
solo el primero y reintentando:

```
1) inference_max_length chico -> ValueError: Cannot allocate KV cache
   for 2611 tokens, max = 2048
2) (resuelto) attn_cache_tokens chico -> mismo error, otro número
3) (resuelto) max_batch_size sigue limitando el PREFILL (el prompt
   completo se procesa de una pasada) -> ValueError: Task size greater
   than max_batch_size (2048), it can't be processed
```

Con los tres en 8192, el cache de atención pasó a **1.75 GiB** en el nodo de
14 bloques y **2.25 GiB** en el de 18 — confirma el cálculo de ~225 KB por
token cada 14 bloques. Quedaron configurables en `run-remote-node.sh`
(`INFERENCE_MAX_LENGTH`, `ATTN_CACHE_TOKENS`, `MAX_BATCH_SIZE`) y no fijos,
porque un nodo chico no debería pagar esa memoria si no la necesita.

Y había un **cuarto** límite en la misma cadena, este no de petals sino de
Docker: con los tres anteriores resueltos, el nodo pasó a fallar con

```
RuntimeError: unable to allocate shared memory(shm) for file
</torch_95_4117754786_4>: No space left on device (28)
```

El nodo pasa los tensores de activación entre su proceso principal y el pool
de inferencia vía memoria compartida (`torch._share_filename_cpu_`), y
`/dev/shm` en un contenedor Docker es **64 MiB por defecto** — no alcanza para
un tensor de un batch de 8192 tokens. `--shm-size 1g` lo resuelve; quedó en
`run-remote-node.sh` como default (`SHM_SIZE`, configurable).

Y un **quinto** eslabón, ya no en los nodos sino en el propio `api-gateway`:
con los cuatro anteriores resueltos, el contenedor del gateway terminó con

```
ExitCode=137 OOMKilled=true
```

El cliente de petals que corre dentro del gateway retiene buffers del prompt
mientras dura la sesión de inferencia, y cada reintento interno ante un fallo
transitorio del lado del servidor (los cuatro de arriba generaron varios,
mientras se iban resolviendo uno por uno) suma más. Con un prompt de ~3000
tokens el límite de memoria que traía el gateway por defecto (3g) no alcanzó.
Se subió el default a **6g** en `run-gateway.sh`.

Con los cinco resueltos, un prompt de **4999 tokens** —bastante más que el
orden de magnitud real de lo que manda aider— se procesó sin errores de
principio a fin en 375s. Verificación no ambigua: el prompt contenía
exactamente 320 funciones definidas y la respuesta fue "320", lo que confirma
que el swarm vio el prompt completo y no una versión truncada.

## La red del nodo importa tanto como su CPU

Midiendo por qué un nodo tardaba 3+ horas en descargar lo que otro bajaba en
minutos, apareció algo que conviene tener en cuenta al sumar máquinas a la red:

| Nodo | Enlace | Bajada real |
|---|---|---|
| ASUS | WiFi 5 GHz | 453 Mbit/s |
| Ubuntu | WiFi 2.4 GHz (adaptador USB, `rt2800usb`) | **12.6 Mbit/s** |

La señal del nodo lento era excelente (`-43 dBm`, `Link Quality 67/70`): no era
distancia ni interferencia, era la banda de 2.4 GHz con un adaptador
802.11n que negocia 65 Mb/s de enlace. La máquina tenía puerto ethernet
(`enp8s0`) sin cable conectado.

Dos consecuencias para el diseño de la red, no solo para esta prueba:

1. **El arranque de un nodo es caro en red.** Bajar su porción del modelo son
   varios GB; con 12 Mbit/s eso son horas. Un nodo que se reincorpora seguido
   (una notebook que se suspende) puede pasar más tiempo descargando que
   sirviendo, si el cache no persiste — de ahí que persistirlo sea crítico.
2. **El transporte entre nodos va por ese mismo enlace**, así que la latencia
   de cada token en el pipeline hereda el peor tramo. No alcanza con mirar
   la CPU al decidir cuántos bloques asignar.

Nota sobre la lentitud de CPU, para no confundir las dos cosas: el mismo nodo
reportaba 56 tok/seg por bloque contra 2733 del Mac, pero eso es cómputo local
puro (`Inference throughput`, medido sin red de por medio) y es consistente con
lo que ya daba con el modelo chico — 203 tok/seg con bloques 3.7× más chicos.
Es la diferencia de CPU entre un i7 de escritorio y un M4, y ningún cambio de
red la afecta.

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
