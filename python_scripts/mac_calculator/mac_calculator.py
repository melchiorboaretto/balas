import sys
import numpy as np
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf

def count_macs(model_path):
    # Sem o delegate XNNPACK: ele falha ao preparar alguns modelos int8 válidos
    # (ex.: MobileNetV1 com TANH) e a contagem só precisa das formas.
    interpreter = tf.lite.Interpreter(
        model_path=str(model_path),
        experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES,
    )
    interpreter.allocate_tensors()  # Needed for shape resolution

    total_macs = 0

    for op in interpreter._get_ops_details():
        op_name = op['op_name']
        inputs = op['inputs']
        outputs = op['outputs']

        layer_macs = 0
        if inputs.size != 0 and outputs.size != 0:
            input_details = interpreter.get_tensor_details()[inputs[0]]
            output_details = interpreter.get_tensor_details()[outputs[0]]

            input_shape = input_details['shape']
            output_shape = output_details['shape']

            if op_name == 'CONV_2D':
                kernel_shape = interpreter.get_tensor_details()[inputs[1]]['shape']
                out_ch, kh, kw, in_ch = kernel_shape
                out_elems = np.prod(output_shape[1:])
                layer_macs = out_elems * kh * kw * in_ch

            elif op_name == 'DEPTHWISE_CONV_2D':
                kernel_shape = interpreter.get_tensor_details()[inputs[1]]['shape']
                x, kh, kw, in_ch = kernel_shape
                out_elems = np.prod(output_shape[1:])
                layer_macs = out_elems * kh * kw

            elif op_name == 'FULLY_CONNECTED':
                weight_shape = interpreter.get_tensor_details()[inputs[1]]['shape']
                in_dim, out_dim = weight_shape
                layer_macs = in_dim * out_dim

        total_macs += layer_macs

    return total_macs

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} model.tflite")
        sys.exit(1)

    model_path = sys.argv[1]
    count_macs(model_path)
