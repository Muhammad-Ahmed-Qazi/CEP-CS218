import pickle

class Node:
    def __init__(self, data=None, freq=0):
        self.data = data
        self.freq = freq
        self.left = None
        self.right = None


def calculate_frequencies(text):
    freq = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    return [Node(ch, fr) for ch, fr in freq.items()]


def build_huffman_tree(nodes):
    nodes = nodes[:]
    while len(nodes) > 1:
        nodes.sort(key=lambda x: x.freq)
        left = nodes.pop(0)
        right = nodes.pop(0)

        merged = Node(freq=left.freq + right.freq)
        merged.left = left
        merged.right = right

        nodes.append(merged)
    return nodes[0]


def generate_codes(node, code="", table=None):
    if table is None:
        table = {}

    if node.data is not None:
        table[node.data] = code
        return table

    generate_codes(node.left, code + "0", table)
    generate_codes(node.right, code + "1", table)

    return table


def huffman_encoding(text):
    nodes = calculate_frequencies(text)
    root = build_huffman_tree(nodes)
    codes = generate_codes(root)
    return codes


def huffman_decoding(encoded, codes):
    reverse = {v: k for k, v in codes.items()}
    cur = ""
    out = []

    for b in encoded:
        cur += b
        if cur in reverse:
            out.append(reverse[cur])
            cur = ""

    return "".join(out)


def compress_file(input_path, output_path):
    with open(input_path, "rb") as f:
        data = f.read()

    # bytes → chars
    text = "".join(chr(b) for b in data)

    codes = huffman_encoding(text)
    encoded = "".join(codes[ch] for ch in text)

    # pack bits → bytes
    b = bytearray()
    for i in range(0, len(encoded), 8):
        byte = encoded[i:i + 8].ljust(8, "0")
        b.append(int(byte, 2))

    with open(output_path, "wb") as f:
        pickle.dump((b, codes, len(encoded)), f)

    return True


def decompress_file(input_path, output_path):
    with open(input_path, "rb") as f:
        b, codes, length = pickle.load(f)

    bits = "".join(format(byte, "08b") for byte in b)
    bits = bits[:length]

    decoded = huffman_decoding(bits, codes)

    data = bytes(ord(c) for c in decoded)

    with open(output_path, "wb") as f:
        f.write(data)

    return output_path
