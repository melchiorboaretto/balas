"""Descrição única da topologia usada pelos builders DSE.

Cada builder monta um ``GraphSpec`` (lista ordenada de camadas com formas
estáticas). A mesma descrição alimenta:

* ``build_keras(spec)``: o modelo Keras que vai para o conversor TFLite;
* ``spec.summary()``: o custo analítico (params, MACs, pico de ativação e a
  sequência de operadores esperada no .tflite), sem precisar do TensorFlow.

Assim o custo usado para filtrar o espaço de busca nunca diverge do modelo
que de fato é gerado. As regras de fusão espelham o conversor do TF 2.21:
BatchNorm é dobrada na conv/dense anterior, ReLU/ReLU6 viram ativação fundida
do CONV_2D/DEPTHWISE_CONV_2D/FULLY_CONNECTED/ADD, Flatten depois de um pooling
1x1 desaparece, e as demais ativações viram operadores separados.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import math
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Ativações
# ---------------------------------------------------------------------------
ACTIVATIONS = ("relu", "relu6", "leaky_relu", "hard_swish", "sigmoid", "tanh")
FUSED_ACTIVATIONS = frozenset({"relu", "relu6"})
DEFAULT_LEAKY_SLOPE = 0.1

# Operador TFLite gerado por cada ativação não fundida (conferido no TF 2.21).
ACTIVATION_TFLITE_OP = {
    "leaky_relu": "LEAKY_RELU",
    "hard_swish": "HARD_SWISH",
    "sigmoid": "LOGISTIC",
    "tanh": "TANH",
}

# Chaves de ativação aceitas por todos os builders (opcionais no grid).
ACTIVATION_GRID_KEYS = ("activation", "leaky_slope")


@dataclass(frozen=True)
class Activation:
    name: str = "relu"
    slope: float | None = None

    @property
    def fused(self) -> bool:
        return self.name in FUSED_ACTIVATIONS


def resolve_activation(config: dict) -> Activation:
    """Lê ``activation``/``leaky_slope`` do config, com default ``relu``."""
    name = config.get("activation")
    name = "relu" if name is None else str(name).strip().lower()
    if name not in ACTIVATIONS:
        raise ValueError(
            f"activation inválida: {name!r}. Opções: {', '.join(ACTIVATIONS)}."
        )
    if name != "leaky_relu":
        return Activation(name)

    slope = config.get("leaky_slope")
    slope = DEFAULT_LEAKY_SLOPE if slope is None else float(slope)
    if not 0.0 < slope < 1.0:
        raise ValueError(f"leaky_slope deve estar em (0, 1); recebido {slope}.")
    return Activation(name, slope)


def canonicalize_activation(config: dict) -> dict:
    """Anula ``leaky_slope`` quando a ativação não é leaky_relu."""
    if "leaky_slope" in config:
        name = config.get("activation")
        if name is None or str(name).strip().lower() != "leaky_relu":
            config["leaky_slope"] = None
    return config


# ---------------------------------------------------------------------------
# IR
# ---------------------------------------------------------------------------
@dataclass
class Node:
    name: str
    op: str
    inputs: list[str]
    shape: tuple[int, ...]
    attrs: dict = field(default_factory=dict)
    params: int = 0
    macs: int = 0


def _same_out(size: int, stride: int) -> int:
    return int(math.ceil(size / stride))


def _pair(value) -> tuple[int, int]:
    if isinstance(value, (tuple, list)):
        return int(value[0]), int(value[1])
    return int(value), int(value)


class GraphSpec:
    """Grafo estático com inferência de forma (batch fixo em 1)."""

    def __init__(self, input_shape: tuple[int, ...], name: str = "model"):
        self.name = name
        self.input_shape = tuple(int(d) for d in input_shape)
        self.nodes: list[Node] = [Node("input", "input", [], self.input_shape)]
        self._by_name = {"input": self.nodes[0]}

    # -- utilitários ---------------------------------------------------------
    @property
    def input(self) -> str:
        return "input"

    def shape(self, name: str) -> tuple[int, ...]:
        return self._by_name[name].shape

    def _add(self, node: Node) -> str:
        if node.name in self._by_name:
            raise ValueError(f"Nome de camada duplicado: {node.name}")
        self.nodes.append(node)
        self._by_name[node.name] = node
        return node.name

    # -- camadas -------------------------------------------------------------
    def conv(self, name, x, filters, kernel, strides=1, *, use_bias=True, **keras):
        h, w, cin = self.shape(x)
        kh, kw = _pair(kernel)
        sh, sw = _pair(strides)
        filters = int(filters)
        if filters < 1 or kh < 1 or kw < 1 or sh < 1 or sw < 1:
            raise ValueError(f"{name}: filtros/kernel/stride devem ser >= 1.")
        ho, wo = _same_out(h, sh), _same_out(w, sw)
        params = kh * kw * cin * filters + (filters if use_bias else 0)
        macs = ho * wo * kh * kw * cin * filters
        attrs = dict(filters=filters, kernel=(kh, kw), strides=(sh, sw),
                     use_bias=use_bias, keras=keras)
        return self._add(Node(name, "conv", [x], (ho, wo, filters), attrs, params, macs))

    def dwconv(self, name, x, kernel, strides=1, **keras):
        h, w, c = self.shape(x)
        kh, kw = _pair(kernel)
        sh, sw = _pair(strides)
        if kh < 1 or kw < 1 or sh < 1 or sw < 1:
            raise ValueError(f"{name}: kernel/stride devem ser >= 1.")
        ho, wo = _same_out(h, sh), _same_out(w, sw)
        params = kh * kw * c + c
        macs = ho * wo * kh * kw * c
        attrs = dict(kernel=(kh, kw), strides=(sh, sw), keras=keras)
        return self._add(Node(name, "dwconv", [x], (ho, wo, c), attrs, params, macs))

    def dense(self, name, x, units, *, activation=None, **keras):
        n_in = int(math.prod(self.shape(x)))
        units = int(units)
        if units < 1:
            raise ValueError(f"{name}: units deve ser >= 1.")
        params = n_in * units + units
        macs = n_in * units
        attrs = dict(units=units, activation=activation, keras=keras)
        return self._add(Node(name, "dense", [x], (units,), attrs, params, macs))

    def bn(self, name, x):
        return self._add(Node(name, "bn", [x], self.shape(x)))

    def act(self, name, x, activation: Activation):
        return self._add(
            Node(name, "act", [x], self.shape(x), dict(activation=activation))
        )

    def add(self, name, a, b):
        if self.shape(a) != self.shape(b):
            raise ValueError(f"{name}: formas incompatíveis {self.shape(a)} vs {self.shape(b)}")
        return self._add(Node(name, "add", [a, b], self.shape(a)))

    def avgpool(self, name, x, pool):
        h, w, c = self.shape(x)
        ph, pw = _pair(pool)
        ho, wo = max(1, (h - ph) // ph + 1), max(1, (w - pw) // pw + 1)
        return self._add(Node(name, "avgpool", [x], (ho, wo, c), dict(pool=(ph, pw))))

    def flatten(self, name, x):
        return self._add(Node(name, "flatten", [x], (int(math.prod(self.shape(x))),)))

    # -- custo analítico -----------------------------------------------------
    def summary(self) -> dict:
        """Params, MACs, pico de ativação int8 e operadores TFLite esperados."""
        alias: dict[str, str] = {"input": "input"}
        consumers: dict[str, int] = {}
        for node in self.nodes:
            for i in node.inputs:
                consumers[i] = consumers.get(i, 0) + 1

        ops: list[tuple[str, list[str], str]] = []  # (op_name, inputs, output)
        sizes: dict[str, int] = {"input": int(math.prod(self.input_shape))}
        producer_op: dict[str, str] = {}

        for node in self.nodes[1:]:
            ins = [alias[i] for i in node.inputs]
            size = int(math.prod(node.shape))
            if node.op == "bn":
                alias[node.name] = ins[0]
                continue
            if node.op == "flatten":
                # O conversor remove o RESHAPE após pooling global; o tensor é o mesmo.
                alias[node.name] = ins[0]
                continue
            if node.op == "act":
                act: Activation = node.attrs["activation"]
                src = ins[0]
                fusable = producer_op.get(src) in {"CONV_2D", "DEPTHWISE_CONV_2D",
                                                   "FULLY_CONNECTED", "ADD"}
                if act.fused and fusable and consumers.get(node.inputs[0], 0) == 1:
                    alias[node.name] = src
                    continue
                op_name = ACTIVATION_TFLITE_OP.get(act.name, act.name.upper())
            else:
                op_name = {
                    "conv": "CONV_2D",
                    "dwconv": "DEPTHWISE_CONV_2D",
                    "dense": "FULLY_CONNECTED",
                    "add": "ADD",
                    "avgpool": "AVERAGE_POOL_2D",
                }[node.op]

            out = node.name
            ops.append((op_name, ins, out))
            sizes[out] = size
            producer_op[out] = op_name
            alias[node.name] = out

            if node.op == "dense" and node.attrs.get("activation") == "softmax":
                sm = f"{node.name}__softmax"
                ops.append(("SOFTMAX", [out], sm))
                sizes[sm] = size
                producer_op[sm] = "SOFTMAX"
                alias[node.name] = sm

        # Liveness: um tensor vive do op que o produz até o último op que o lê.
        first = {"input": -1}
        last = {"input": -1}
        for k, (_, ins, out) in enumerate(ops):
            first.setdefault(out, k)
            last[out] = max(last.get(out, k), k)
            for t in ins:
                last[t] = max(last.get(t, k), k)
        final_out = ops[-1][2] if ops else "input"
        last[final_out] = len(ops)

        peak = 0
        for k in range(len(ops)):
            live = sum(sizes[t] for t in first if first[t] <= k <= last[t])
            peak = max(peak, live)
        # O TFLM não atinge o pico de liveness: o GreedyMemoryPlanner fragmenta.
        # Ordem do AddBuffer = ordem dos tensores no flatbuffer, que o conversor
        # gera na ordem de criação (entrada, depois a saída de cada op).
        planned = greedy_memory_plan(
            [(_align16(sizes[t]), first[t], last[t]) for t in first]
        )

        params = sum(n.params for n in self.nodes)
        macs = sum(n.macs for n in self.nodes)

        # Dados para o modelo de overhead do TFLM (mesma fórmula do tflite_inspect).
        output_channels = 0
        max_scratch = 0
        const_tensors = 0
        for node in self.nodes[1:]:
            if node.op in ("conv", "dwconv", "dense"):
                cout = node.shape[-1]
                output_channels += cout
                const_tensors += 2
                if node.op == "conv":
                    kh, kw = node.attrs["kernel"]
                    cin = self._by_name[node.inputs[0]].shape[-1]
                    if kh * kw > 1:
                        max_scratch = max(max_scratch, 2 * cin * kh * kw * 2)
                elif node.op == "dwconv":
                    kh, kw = node.attrs["kernel"]
                    max_scratch = max(max_scratch, cout * kh * kw * 2)
            elif node.op == "avgpool":
                max_scratch = max(max_scratch, self._by_name[node.inputs[0]].shape[-1] * 4)
        num_tensors = len(sizes) + const_tensors
        arena = tflm_arena_from_parts(planned, output_channels, num_tensors, len(ops), max_scratch)

        return {
            "params": int(params),
            "macs": int(macs),
            "peak_activation_bytes": int(peak),
            "planned_activation_bytes": int(planned),
            "input_elements": int(math.prod(self.input_shape)),
            "input_shape": self.input_shape,
            "output_elements": int(sizes.get(final_out, 0)),
            "ops": [op for op, _, _ in ops],
            "non_fused_activation_ops": sum(
                1 for op, _, _ in ops if op in ACTIVATION_TFLITE_OP.values()
            ),
            "output_channels": int(output_channels),
            "max_scratch_bytes": int(max_scratch),
            "arena_estimate": int(arena),
        }


def _align16(value: int) -> int:
    return (int(value) + 15) // 16 * 16


def greedy_memory_plan(buffers) -> int:
    """Réplica do ``tflite::GreedyMemoryPlanner`` (TFLM). Devolve o high-water mark.

    ``buffers`` = lista de (tamanho alinhado a 16, primeiro uso, último uso) na
    ordem em que o TFLM chama ``AddBuffer`` (índice do tensor no flatbuffer).
    Os intervalos são inclusivos. O planner preenche a lista a partir do fim,
    ordena por tamanho decrescente (ordenação estável) e põe cada buffer no
    primeiro buraco, em ordem de offset, que não conflite no tempo. Conferido
    contra o ``print_allocations`` do pacote ``tflite-micro``: igual em 60/60
    modelos (4 benchmarks × 7 ativações + sorteados).
    """
    n = len(buffers)
    if n == 0:
        return 0
    ids = sorted(reversed(range(n)), key=lambda i: -buffers[i][0])
    offsets = {ids[0]: 0}
    placed = [(0, ids[0])]  # (offset, id), ordenado por offset
    for bid in ids[1:]:
        size, first, last = buffers[bid]
        candidate, prior = 0, None
        while True:
            nxt = None
            for j in range(0 if prior is None else prior + 1, len(placed)):
                p_first, p_last = buffers[placed[j][1]][1:]
                if not (p_last < first or last < p_first):
                    nxt = j
                    break
            if prior is not None:
                candidate = max(candidate, placed[prior][0] + buffers[placed[prior][1]][0])
            if nxt is None or placed[nxt][0] - candidate >= size:
                break
            prior = nxt
        offsets[bid] = candidate
        k = 0
        if placed[0][0] > candidate:
            placed.insert(0, (candidate, bid))
        else:
            while k + 1 < len(placed) and placed[k + 1][0] <= candidate:
                k += 1
            placed.insert(k + 1, (candidate, bid))
    return max(offsets[i] + buffers[i][0] for i in range(n))


def tflm_arena_from_parts(planned, output_channels, num_tensors, num_ops, max_scratch) -> int:
    """Arena do TFLM ≈ ativações planejadas + persistente por canal + metadados + scratch.

    ``planned`` é o high-water mark do GreedyMemoryPlanner (``greedy_memory_plan``),
    não o pico de liveness: no MobileNetV1 de referência o planner usa 73.728 B
    contra 55.296 B de pico, e usar o pico subestimava a arena em até ~20%.
    O scratch do CMSIS-NN entra por cima (conservador). Calibrado com o ResNet8
    de referência (planner = pico = 49.152 B; stm32tflm = 56.832 B; arena_used
    real no STM32 = 54.708 B). Usado pelo fallback do arena_estimator e pelo
    space_report.
    """
    persistent = 8 * output_channels  # multiplicador + shift int32 por canal
    # Por tensor: TfLiteEvalTensor (12 B em 32 bits) + folga. Por op:
    # NodeAndRegistration (32 B em 32 bits) + OpData do kernel (~40-60 B).
    # 96 B/op (era 64): com 64, o menor IC da faixa ficava ~0,4% abaixo do pior
    # caso estimado para 32 bits (tail medido no TFLM 64 bits, escalado).
    metadata = 16 * num_tensors + 96 * num_ops
    return _align16(_align16(planned) + persistent + metadata + max_scratch + 1024)


# ---------------------------------------------------------------------------
# Keras
# ---------------------------------------------------------------------------
def _keras_kwargs(tf, raw: dict) -> dict:
    kwargs = dict(raw)
    l2 = kwargs.pop("l2", None)
    if l2:
        kwargs["kernel_regularizer"] = tf.keras.regularizers.l2(l2)
    return kwargs


def _keras_activation_layer(tf, act: Activation, name: str):
    layers = tf.keras.layers
    if act.name == "relu":
        return layers.Activation("relu", name=name)
    if act.name == "relu6":
        return layers.ReLU(max_value=6.0, name=name)
    if act.name == "leaky_relu":
        return layers.LeakyReLU(negative_slope=act.slope, name=name)
    return layers.Activation(act.name, name=name)


def spec_seed(spec: GraphSpec) -> int:
    """Seed derivada da topologia: o mesmo modelo sempre recebe os mesmos pesos."""
    signature = repr([(n.name, n.op, n.inputs, n.shape, sorted(
        (k, repr(v)) for k, v in n.attrs.items())) for n in spec.nodes])
    return int(hashlib.sha1(signature.encode("utf-8")).hexdigest()[:8], 16)


def build_keras(spec: GraphSpec, model_name: str = "model"):
    """Instancia o modelo Keras descrito por ``spec`` (batch_size=1).

    Os pesos são aleatórios mas determinísticos (seed da topologia), para que o
    mesmo config gere sempre o mesmo .tflite (reprodutibilidade dos artefatos).
    """
    import tensorflow as tf

    tf.keras.utils.set_random_seed(spec_seed(spec))
    layers = tf.keras.layers
    tensors = {}
    inputs = tf.keras.Input(shape=spec.input_shape, batch_size=1, name="input")
    tensors["input"] = inputs

    for node in spec.nodes[1:]:
        x = [tensors[i] for i in node.inputs]
        a = node.attrs
        if node.op == "conv":
            layer = layers.Conv2D(
                a["filters"], a["kernel"], strides=a["strides"], padding="same",
                use_bias=a["use_bias"], name=node.name, **_keras_kwargs(tf, a["keras"]),
            )
        elif node.op == "dwconv":
            layer = layers.DepthwiseConv2D(
                a["kernel"], strides=a["strides"], padding="same", name=node.name,
                **_keras_kwargs(tf, a["keras"]),
            )
        elif node.op == "dense":
            layer = layers.Dense(
                a["units"], activation=a["activation"], name=node.name,
                **_keras_kwargs(tf, a["keras"]),
            )
        elif node.op == "bn":
            layer = layers.BatchNormalization(name=node.name)
        elif node.op == "act":
            layer = _keras_activation_layer(tf, a["activation"], node.name)
        elif node.op == "add":
            layer = layers.Add(name=node.name)
        elif node.op == "avgpool":
            layer = layers.AveragePooling2D(pool_size=a["pool"], name=node.name)
        elif node.op == "flatten":
            layer = layers.Flatten(name=node.name)
        else:  # pragma: no cover - IR inválido
            raise ValueError(f"Operação desconhecida no IR: {node.op}")
        tensors[node.name] = layer(x if node.op == "add" else x[0])

    return tf.keras.Model(inputs=inputs, outputs=tensors[spec.nodes[-1].name], name=model_name)


# ---------------------------------------------------------------------------
# Quantização int8 (comum aos 4 builders)
# ---------------------------------------------------------------------------
REPRESENTATIVE_SAMPLES = 100
REPRESENTATIVE_SEED = 72


def safe_tflite_filename(variant_name: str) -> str:
    """Nome de arquivo seguro e limitado (o nome completo pode passar de 255 bytes)."""
    sanitized = "".join(
        char if char.isalnum() or char in "-_." else "_" for char in variant_name
    )
    if not sanitized:
        sanitized = "model"
    if len(sanitized) > 180:
        digest = hashlib.sha1(variant_name.encode("utf-8")).hexdigest()[:16]
        sanitized = f"model_{digest}"
    return f"{sanitized}.tflite"


def quantize_to_tflite(model, variant_name: str, tmp_dir: Path) -> Path:
    """Converte para TFLite int8 com calibração sintética determinística.

    Pesos e amostras aleatórios servem para medir MACs, latência e arena; a
    acurácia resultante não é representativa.
    """
    import numpy as np
    import tensorflow as tf

    input_shape = tuple(int(d) for d in model.inputs[0].shape[1:])
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def representative_dataset_gen():
        rng = np.random.default_rng(REPRESENTATIVE_SEED)
        for _ in range(REPRESENTATIVE_SAMPLES):
            yield [rng.uniform(0.0, 1.0, size=(1,) + input_shape).astype(np.float32)]

    converter.representative_dataset = representative_dataset_gen
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    # Os .tflite oficiais têm FULLY_CONNECTED quantizado por tensor; o TF atual
    # quantiza camadas densas por canal por padrão.
    converter._experimental_disable_per_channel_quantization_for_dense_layers = True

    # O export interno do Keras imprime centenas de linhas ("Saved artifact",
    # "Captures: TensorSpec...") no stdout a cada modelo; isso afogava o log do
    # loop de DSE. Erros continuam sendo levantados normalmente.
    with contextlib.redirect_stdout(io.StringIO()):
        tflite_bytes = converter.convert()
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tflite_path = tmp_dir / safe_tflite_filename(variant_name)
    tflite_path.write_bytes(tflite_bytes)
    return tflite_path
