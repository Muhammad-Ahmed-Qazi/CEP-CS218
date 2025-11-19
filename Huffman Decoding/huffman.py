import os
import heapq # Assuming this is available from the standard library

### HUFFMAN NODE CLASS ###
class HuffmanNode:
    """Represents a node in the Huffman tree."""
    def __init__(self, byte=None, freq=0, left=None, right=None):
        # byte: The actual byte value (0-255). None for internal nodes.
        self.byte = byte
        # freq: The frequency of the byte or the combined frequency of its children.
        self.freq = freq
        # left/right: Pointers to child nodes.
        self.left = left
        self.right = right

    # Custom comparison method is needed for the priority queue logic (min-heap)
    # This allows Python's heapq to compare nodes based on frequency.
    def __lt__(self, other):
        return self.freq < other.freq
    
### FREQUENCY COUNTING ###
def calculate_frequency(file_path):
    """Calculates the frequency of each byte in the given file."""
    # Initialize a dictionary to store byte frequencies (keys: 0-255, values: count)
    frequency = {}
    
    try:
        # Open the file in read-binary mode ('rb')
        with open(file_path, 'rb') as file:
            # Read the file in chunks or one byte at a time
            byte = file.read(1)
            while byte:
                # byte is a 'bytes' object (e.g., b'\x0a'). Use byte[0] to get the int value (0-255).
                byte_int = byte[0]
                frequency[byte_int] = frequency.get(byte_int, 0) + 1
                byte = file.read(1)
                
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None
        
    return frequency

### TREE AND CODE GENERATION ###
def build_huffman_tree_and_codes(frequency):
    """
    Builds the Huffman tree and generates the binary codes for each byte.
    Returns the root of the tree and the code lookup table.
    """
    # 1. Create a list of leaf nodes (priority queue)
    priority_queue = []
    for byte, freq in frequency.items():
        node = HuffmanNode(byte=byte, freq=freq)
        # heapq uses a list to simulate a min-heap
        heapq.heappush(priority_queue, node)

    # Handle edge case: empty file or file with only one unique byte
    if not priority_queue:
        return None, {}
    if len(priority_queue) == 1:
        # Special case: Assign '0' as the code for the single byte
        root = priority_queue[0]
        return root, {root.byte: '0'}

    # 2. Build the tree by repeatedly merging the two lowest frequency nodes
    while len(priority_queue) > 1:
        # Get the two lowest frequency nodes
        left = heapq.heappop(priority_queue)
        right = heapq.heappop(priority_queue)

        # Create a new internal node
        merged_freq = left.freq + right.freq
        parent = HuffmanNode(freq=merged_freq, left=left, right=right)

        # Add the new node back to the queue
        heapq.heappush(priority_queue, parent)

    # The last node remaining is the root of the Huffman tree
    root = priority_queue[0]
    
    # 3. Generate codes recursively
    huffman_codes = {}
    
    def generate_codes_recursive(node, current_code):
        # Stop at a leaf node (a byte)
        if node.byte is not None:
            huffman_codes[node.byte] = current_code
            return
        
        # Traverse left (add '0')
        if node.left:
            generate_codes_recursive(node.left, current_code + '0')
        # Traverse right (add '1')
        if node.right:
            generate_codes_recursive(node.right, current_code + '1')

    # Start traversal from the root with an empty code string
    generate_codes_recursive(root, "")
    
    return root, huffman_codes

### REVISED COMPRESS_FILE FUNCTION ###

def compress_file(input_path):
    """
    Compresses the file using Huffman coding, including a self-contained header.
    """
    filename, ext = os.path.splitext(input_path)
    output_path = filename + ext + '.huff'
    
    frequency = calculate_frequency(input_path)
    if not frequency:
        return "Compression failed: Could not read file or file is empty."
        
    # Build tree and codes (we'll need the total file size and codes)
    root, huffman_codes = build_huffman_tree_and_codes(frequency)
    
    # These variables manage the bit packing process (same as before)
    buffer = 0  
    bit_count = 0
    padding_bits = 0 # We need this to calculate and write to the header

    try:
        with open(output_path, 'wb') as output_file:
            
            # --- PHASE 1: Bit Packing and Writing (Temporary Memory) ---
            encoded_data = bytearray()
            
            with open(input_path, 'rb') as input_file:
                input_byte = input_file.read(1)
                while input_byte:
                    byte_int = input_byte[0]
                    code = huffman_codes[byte_int]
                    
                    for bit in code:
                        buffer = (buffer << 1) | int(bit)
                        bit_count += 1
                        
                        if bit_count == 8:
                            encoded_data.append(buffer) # Save packed byte
                            buffer = 0
                            bit_count = 0

                    input_byte = input_file.read(1)
            
            # --- PHASE 2: Handle Final Padding and Calculate Padding Size ---
            if bit_count > 0:
                padding_bits = 8 - bit_count
                # Shift buffer left to insert padding zeros
                buffer = buffer << padding_bits
                encoded_data.append(buffer)
            
            # --- PHASE 3: Write the Complete Header ---
            
            # 1. Write the Padding Size (1 byte is enough, max padding is 7 bits)
            output_file.write(padding_bits.to_bytes(1, byteorder='big')) 
            
            # 2. Write the Number of Unique Bytes (2 bytes, supports up to 65535 unique codes, which is ample)
            num_unique_bytes = len(frequency)
            output_file.write(num_unique_bytes.to_bytes(2, byteorder='big')) 

            # 3. Write the Frequency Table
            for byte_val, count in frequency.items():
                # Byte Value (1 byte)
                output_file.write(byte_val.to_bytes(1, byteorder='big')) 
                
                # Frequency Count (4 bytes, supports files up to 4GB)
                output_file.write(count.to_bytes(4, byteorder='big')) 

            # --- PHASE 4: Write the Encoded Data ---
            output_file.write(encoded_data)
                
        return f"Successfully compressed {input_path} to {output_path}."

    except Exception as e:
        return f"An error occurred during compression: {e}"

# Example Usage:
# result = compress_file('path/to/your/document.txt')
# print(result)

### REVISED DECOMPRESS_FILE FUNCTION ###

def decompress_file(compressed_path, output_path):
    """
    Decompresses the Huffman encoded file using the self-contained header.
    """
    if not compressed_path.endswith('.huff'):
        return "Decompression failed: Input file must have the '.huff' extension."
        
    original_path = output_path
    
    try:
        with open(compressed_path, 'rb') as input_file, open(output_path, 'wb') as output_file:
            
            # --- PHASE 1: Read and Reconstruct Header Data ---
            
            # 1. Read Padding Size (1 byte)
            padding_bytes = input_file.read(1)
            if not padding_bytes: return "Decompression error: File is empty or truncated."
            padding_bits = int.from_bytes(padding_bytes, byteorder='big') 

            # 2. Read Number of Unique Bytes (2 bytes)
            num_bytes = input_file.read(2)
            if len(num_bytes) < 2: return "Decompression error: Header truncated."
            num_unique_bytes = int.from_bytes(num_bytes, byteorder='big')
            
            # 3. Read Frequency Table and Calculate Total Size
            frequency = {}
            total_size = 0
            for _ in range(num_unique_bytes):
                # Byte Value (1 byte)
                byte_val = input_file.read(1)
                if len(byte_val) < 1: return "Decompression error: Frequency table truncated (byte value)."
                byte_int = int.from_bytes(byte_val, byteorder='big')
                
                # Frequency Count (4 bytes)
                count_bytes = input_file.read(4)
                if len(count_bytes) < 4: return "Decompression error: Frequency table truncated (count)."
                count = int.from_bytes(count_bytes, byteorder='big')
                
                frequency[byte_int] = count
                total_size += count

            # 4. Rebuild the Huffman Tree
            root, _ = build_huffman_tree_and_codes(frequency)
            if not root: return "Decompression error: Could not rebuild Huffman tree."

            # --- PHASE 2: Bit Unpacking and Decoding ---
            
            current_node = root
            decoded_byte_count = 0
            
            # Read the encoded data byte by byte
            while decoded_byte_count < total_size:
                encoded_byte = input_file.read(1)
                if not encoded_byte:
                    break
                
                byte_value = encoded_byte[0]
                
                # Determine the number of bits to process for this byte
                bits_to_process = 8
                # If this is the *last* byte of the file, we must exclude the padding bits
                if input_file.peek(1) == b'':
                     bits_to_process -= padding_bits
                
                # Process the bits
                for i in range(bits_to_process):
                    bit = (byte_value >> (7 - i)) & 1 # Get the i-th bit
                    
                    if bit == 0:
                        current_node = current_node.left
                    else: 
                        current_node = current_node.right
                        
                    # Check for leaf node
                    if current_node.byte is not None:
                        output_file.write(current_node.byte.to_bytes(1, byteorder='big'))
                        decoded_byte_count += 1
                        current_node = root
                        
                        if decoded_byte_count >= total_size:
                            break # Finish decoding
                            
            if decoded_byte_count == total_size:
                return f"Successfully decompressed {compressed_path} to {original_path}."
            else:
                 return f"Decompression finished, but byte count mismatch. Expected {total_size}, found {decoded_byte_count}."
                         
    except Exception as e:
        return f"An error occurred during decompression: {e}"


def main():
    """
    Main function to test compression and decompression.
    """
    
    # ------------------
    # CONFIGURATION
    # ------------------
    
    # !!! IMPORTANT !!!
    # 1. Replace this with a path to a test file (text, PDF, or DOCX)
    TEST_FILE_PATH = "Sessional Activity sana.docx"  
    
    # 2. Define the path for the compressed file
    # This automatically uses the file extension logic you implemented.
    COMPRESSED_FILE_PATH = TEST_FILE_PATH + ".huff"
    
    # 3. Define the path for the decompressed output file
    # This ensures we don't overwrite the original during testing.
    DECOMPRESSED_FILE_PATH = "decompressed_" + os.path.basename(TEST_FILE_PATH)
    
    
    print("-" * 50)
    print(f"Starting Huffman Test on: {TEST_FILE_PATH}")
    print("-" * 50)

    # --- Step 1: Check File Existence ---
    if not os.path.exists(TEST_FILE_PATH):
        print(f"🚨 ERROR: Test file not found at '{TEST_FILE_PATH}'.")
        print("Please create this file or update the TEST_FILE_PATH variable.")
        return

    original_size = os.path.getsize(TEST_FILE_PATH)
    print(f"Original Size: {original_size} bytes")

    
    # --- Step 2: COMPRESSION ---
    print("\n[COMPRESSION STARTED]")
    compression_result = compress_file(TEST_FILE_PATH)
    print(compression_result)
    
    if os.path.exists(COMPRESSED_FILE_PATH):
        compressed_size = os.path.getsize(COMPRESSED_FILE_PATH)
        print(f"Compressed Size: {compressed_size} bytes")
        
        # Calculate Compression Ratio (higher is better)
        if original_size > 0:
            ratio = 100 * (1 - compressed_size / original_size)
            print(f"Compression achieved: {ratio:.2f}% reduction.")
            
        print("-" * 50)
        
    else:
        print("❌ Compression failed: Compressed file not created.")
        return

    
    # --- Step 3: DECOMPRESSION ---
    print("\n[DECOMPRESSION STARTED]")
    
    # Note: We pass the COMPRESSED_FILE_PATH to the decompressor.
    # The decompressor automatically determines the output path based on the filename.
    # Pass the defined output path
    decompression_result = decompress_file(COMPRESSED_FILE_PATH, DECOMPRESSED_FILE_PATH) 
    print(decompression_result)
    
    
    # --- Step 4: VERIFICATION ---
    print("\n[VERIFICATION]")
    
    if os.path.exists(TEST_FILE_PATH) and os.path.exists(DECOMPRESSED_FILE_PATH):
        # We need a simple way to verify the file content is identical
        import filecmp
        
        # Check if the decompressed file is the same size as the original
        decompressed_size = os.path.getsize(DECOMPRESSED_FILE_PATH)
        
        # We will compare the decompressed file's content to the original file's content
        if filecmp.cmp(TEST_FILE_PATH, DECOMPRESSED_FILE_PATH):
            print("✅ SUCCESS: Decompressed file is IDENTICAL to the original.")
        else:
            print("❌ FAILURE: Decompressed file content MISMATCHES the original.")

        # Clean up the test files (optional, but good practice)
        # os.remove(COMPRESSED_FILE_PATH)
        # os.remove(DECOMPRESSED_FILE_PATH)
        # print("\nCleaned up compressed and decompressed files.")
        
    else:
        print("❌ Verification failed: Decompressed file not found.")

# This standard Python idiom ensures the 'main' function is called only when 
# the script is executed directly, not when imported as a module.
if __name__ == "__main__":
    main()