import pickle, sys, os

# Defining binary tree nodes for Huffman Decoding
class Node:
    def __init__(self, data=None, freq=0):
        self.data = data
        self.freq = freq
        self.left = None
        self.right = None
    
nodes = []

# Function to calculate frequency of each character in the input text
def calculate_frequencies(text):
    freq = {}
    for char in text:
        if char not in freq:
            freq[char] = text.count(char)
            nodes.append(Node(char, freq[char]))

# Function to build the Huffman tree
def build_huffman_tree(nodes):
    while len(nodes) > 1:
        # Sort nodes based on frequency
        nodes.sort(key=lambda x: x.freq)
        left = nodes.pop(0)
        right = nodes.pop(0)
    
        # Create a new internal node with these two nodes as children
        merged = Node(freq=left.freq + right.freq)
        merged.left = left
        merged.right = right
    
        # Add the new node back to the list of nodes
        nodes.append(merged)

    # Return the root of the Huffman tree
    return nodes[0] if nodes else None

# Function to generate Huffman codes from the tree
def generate_codes(node, current_code="", codes={}):
    if node is None:
        return

    # If this is a leaf node, store the code
    if node.data is not None:
        codes[node.data] = current_code
        return

    # Traverse left and right children
    generate_codes(node.left, current_code + "0", codes)
    generate_codes(node.right, current_code + "1", codes)

    return codes

# Main function to perform Huffman encoding
def huffman_encoding(text):
    global nodes
    nodes = []

    calculate_frequencies(text)
    root = build_huffman_tree(nodes)
    huffman_codes = generate_codes(root)

    return huffman_codes

def huffman_decoding(encoded_text, huffman_codes):
    current_code = ""
    decoded_chars = []

    # Invert the codes dictionary to get the reverse mapping
    reverse_codes = {v: k for k, v in huffman_codes.items()}

    for bit in encoded_text:
        current_code += bit
        if current_code in reverse_codes:
            decoded_chars.append(reverse_codes[current_code])
            current_code = ""

    return "".join(decoded_chars)

# Functions to handle file compression and decompression
def compress_file(input_path, output_path):
    # Read file as bytes
    with open(input_path, "rb") as f:
        data = f.read()

    # Convert bytes to string of characters (so your Huffman works as-is)
    text = "".join([chr(byte) for byte in data])

    # Get Huffman codes
    huffman_codes = huffman_encoding(text)

    # Encode the text using the codes
    encoded_text = "".join(huffman_codes[char] for char in text)

    # Convert the encoded text (bits) into bytes for writing
    b = bytearray()
    for i in range(0, len(encoded_text), 8):
        byte = encoded_text[i:i+8]
        b.append(int(byte.ljust(8, "0"), 2))

    # Save compressed data and codes
    with open(output_path, "wb") as f:
        pickle.dump((b, huffman_codes, len(encoded_text)), f)

    print(f"✅ Compressed '{input_path}' → '{output_path}'")

def decompress_file(input_path, output_path):
    with open(input_path, "rb") as f:
        b, huffman_codes, encoded_length = pickle.load(f)

    # Convert bytes back into bit string
    bit_string = ""
    for byte in b:
        bit_string += format(byte, "08b")
    bit_string = bit_string[:encoded_length]  # remove padded bits

    # Decode text
    decoded_text = huffman_decoding(bit_string, huffman_codes)

    # Convert back to bytes and write
    data = bytes([ord(ch) for ch in decoded_text])
    with open(output_path, "wb") as f:
        f.write(data)

    print(f"✅ Decompressed '{input_path}' → '{output_path}'")

# Main execution
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python huffman.py [c|d] input_file output_file")
        sys.exit(1)

    mode = sys.argv[1]
    inp = sys.argv[2]
    outp = sys.argv[3]

    if mode == "c":
        compress_file(inp, outp)
    elif mode == "d":
        decompress_file(inp, outp)
    else:
        print("Invalid mode. Use 'c' for compression, 'd' for decompression.")
