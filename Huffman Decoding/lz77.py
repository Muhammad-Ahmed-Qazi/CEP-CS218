import os
import struct

# --- CONSTANTS ---
# Max distance fits into 12 bits (2^12 - 1 = 4095). CHANGED FROM 4096 to prevent distance 0 encoding.
SEARCH_WINDOW_SIZE = 4095 
LOOKAHEAD_SIZE = 15 
MIN_MATCH_LENGTH = 3 

# --- CORE LZ77 LOGIC ---

def find_longest_match(window, lookahead):
    """
    Searches the search window for the longest sequence that matches 
    the beginning of the lookahead buffer.
    
    Includes first-byte filtering optimization and safer loop bounds.
    Returns (distance, length)
    """
    max_length = 0
    best_distance = 0
    
    if not lookahead or len(lookahead) < MIN_MATCH_LENGTH:
        return 0, 0

    first_byte_lookahead = lookahead[0]
    
    # Iterate through all possible starting positions in the search window
    for index_in_window in range(len(window)):
        
        # CRITICAL OPTIMIZATION: First-Byte Filtering
        if window[index_in_window] != first_byte_lookahead:
            continue

        # --- Safer Inner Loop for Match Length ---
        current_match_length = 0
        
        # Max possible match length is the shortest of:
        # 1. The lookahead buffer size (len(lookahead))
        # 2. The remaining size of the search window from this index (len(window) - index_in_window)
        limit = min(len(lookahead), len(window) - index_in_window)

        for j in range(limit):
            if window[index_in_window + j] == lookahead[j]:
                current_match_length += 1
            else:
                break
        # --- End Safer Inner Loop ---

        if current_match_length > max_length:
            max_length = current_match_length
            best_distance = len(window) - index_in_window
            
    if max_length < MIN_MATCH_LENGTH: 
        return 0, 0
        
    return best_distance, max_length

def encode_lz77(data):
    """Encodes a byte string using the LZ77 algorithm, generating tokens."""
    encoded_tokens = []
    i = 0  
    N = len(data)
    
    while i < N:
        window_start = max(0, i - SEARCH_WINDOW_SIZE)
        search_window = data[window_start:i] 
        lookahead = data[i : i + LOOKAHEAD_SIZE] 

        distance, length = find_longest_match(search_window, lookahead)
        
        has_next_literal = (i + length) < N
        
        if length >= MIN_MATCH_LENGTH:
            next_literal = data[i + length] if has_next_literal else None
            encoded_tokens.append((distance, length, next_literal))
            i += length + (1 if has_next_literal else 0)
        else:
            encoded_tokens.append((0, 0, data[i]))
            i += 1 

    return encoded_tokens

# --- COMPRESSION FUNCTION ---

def compress_lz77_file(input_path):
    """
    Reads the file, runs LZ77 encoding, and writes the compressed stream with a header.
    """
    filename, ext = os.path.splitext(input_path)
    output_path = filename + ext + '.lz77'
    
    try:
        with open(input_path, 'rb') as f:
            data = f.read()
        if not data:
            return "Compression failed: File is empty."
    except Exception as e:
        return f"Error reading input file: {e}"

    original_size = len(data)
    
    print(f"\n[LZ77 COMPRESSION]: Encoding {input_path} ({original_size} bytes)...")
    tokens = encode_lz77(data)
    
    # --- Bit Packing Logic (Local Helper) ---
    buffer = 0  
    bit_count = 0
    encoded_data = bytearray()
    
    def pack_and_write_to_mem(value, num_bits):
        nonlocal buffer, bit_count
        
        for i in range(num_bits - 1, -1, -1):
            bit = (value >> i) & 1
            buffer = (buffer << 1) | bit
            bit_count += 1
            
            if bit_count == 8:
                encoded_data.append(buffer)
                buffer = 0
                bit_count = 0

    try:
        # Generate the encoded data bit stream
        for token in tokens:
            distance, length, next_literal = token
            
            if length >= MIN_MATCH_LENGTH:
                # Match Token: 1 (Flag) + 12 (Distance) + 4 (Length) + [8 (Literal)]
                pack_and_write_to_mem(1, 1)  # Flag: 1 (Match)
                pack_and_write_to_mem(distance, 12)
                pack_and_write_to_mem(length - MIN_MATCH_LENGTH, 4) 
                
                # IMPORTANT: Only write the next literal if it exists (i.e., not the end of file)
                if next_literal is not None:
                    pack_and_write_to_mem(next_literal, 8) 
                
            else:
                # Literal Token: 0 (Flag) + 8 (Literal)
                literal_byte = next_literal 
                pack_and_write_to_mem(0, 1)  # Flag: 0 (Literal)
                pack_and_write_to_mem(literal_byte, 8)

        # Handle Final Padding
        padding_bits = 0
        if bit_count > 0:
            padding_bits = 8 - bit_count
            buffer = buffer << padding_bits
            encoded_data.append(buffer)
        
        # Write to File: Header + Data
        with open(output_path, 'wb') as output_file:
            # HEADER STRUCTURE
            output_file.write(original_size.to_bytes(8, byteorder='big')) 
            output_file.write(padding_bits.to_bytes(1, byteorder='big'))  

            output_file.write(encoded_data)
        
        compressed_size = os.path.getsize(output_path)
        compression_ratio = (1 - compressed_size / original_size) * 100
            
        return f"✅ SUCCESS: Compressed {original_size} bytes to {compressed_size} bytes ({compression_ratio:.2f}% compression). File: {output_path}"

    except Exception as e:
        return f"❌ FAILURE: An error occurred during LZ77 compression: {e}"


# --- DECOMPRESSION FUNCTION (Absolute Bit Indexing) ---

def decompress_lz77_file(compressed_path):
    """
    Decompresses the LZ77 encoded file using the self-contained header.
    """
    if not compressed_path.endswith('.lz77'):
        return "Decompression failed: Input file must have the '.lz77' extension."
        
    original_path = os.path.splitext(compressed_path)[0]
    
    try:
        with open(compressed_path, 'rb') as input_file:
            
            # --- PHASE 1: Read Header ---
            size_bytes = input_file.read(8)
            if len(size_bytes) < 8: return "Decompression error: Header truncated (size)."
            original_size = int.from_bytes(size_bytes, byteorder='big')
            
            padding_bytes = input_file.read(1)
            if len(padding_bytes) < 1: return "Decompression error: Header truncated (padding)."
            padding_bits = int.from_bytes(padding_bytes, byteorder='big') 

            # Read the entire compressed data segment into memory
            compressed_data = input_file.read()
            
            # Total size of the data segment in *useful* bits
            MAX_BITS = len(compressed_data) * 8 - padding_bits
            current_bit_index = 0
            
            # --- PHASE 2: Bit Unpacking and Decoding ---
            
            output_buffer = bytearray()
            decoded_count = 0
            
            def read_bits(num_bits):
                nonlocal current_bit_index
                
                # Check 1: Do we have enough bits left?
                if current_bit_index + num_bits > MAX_BITS:
                    current_bit_index = MAX_BITS 
                    return None 
                
                result = 0
                for _ in range(num_bits):
                    byte_index = current_bit_index // 8
                    bit_in_byte = current_bit_index % 8
                    
                    # Read the bit from the byte in memory
                    byte_value = compressed_data[byte_index]
                    # Read from MSB (index 0) to LSB (index 7)
                    bit = (byte_value >> (7 - bit_in_byte)) & 1
                    
                    result = (result << 1) | bit
                    current_bit_index += 1

                return result


            while decoded_count < original_size:
                
                flag = read_bits(1)
                # If we run out of bits, we must break
                if flag is None: break 
                
                if flag == 0:
                    # --- LITERAL TOKEN (9 bits) ---
                    literal = read_bits(8)
                    if literal is None: break
                    
                    output_buffer.append(literal)
                    decoded_count += 1
                    
                elif flag == 1:
                    # --- MATCH TOKEN (17 or 25 bits) ---
                    
                    distance = read_bits(12)
                    if distance is None: break
                    
                    length_code = read_bits(4)
                    if length_code is None: break
                    
                    length = length_code + MIN_MATCH_LENGTH

                    
                    # Determine if the 8-bit next_literal was encoded
                    # It was encoded if the match doesn't fill up the rest of the file
                    will_read_literal = (decoded_count + length) < original_size
                    literal_read_value = None
                    
                    if will_read_literal:
                        literal_read_value = read_bits(8)
                        if literal_read_value is None: break
                    
                    # 2. Copy the Match Sequence
                    
                    # Safety Check for index out of range error (Distance 0 is invalid)
                    if distance == 0 or distance > len(output_buffer):
                         raise ValueError(f"Decompression Failure: Invalid distance ({distance}) pointing outside the decoded buffer. Stream misalignment suspected.")

                    start_copy = len(output_buffer) - distance
                    
                    for _ in range(length):
                        
                        # Explicit check before copying to prevent reading past original_size
                        if decoded_count >= original_size: break
                        
                        # Copy the byte from the position in the *current* output buffer
                        byte_to_copy = output_buffer[start_copy]
                        output_buffer.append(byte_to_copy)
                        start_copy += 1
                        decoded_count += 1
                        
                    # 3. Write the Next Literal Byte (only if read and if we haven't hit the end)
                    if decoded_count < original_size and literal_read_value is not None:
                        output_buffer.append(literal_read_value)
                        decoded_count += 1
                
                # CRITICAL FIX: Break immediately if we have decoded all the data
                # This prevents reading the flag for a non-existent next token
                if decoded_count >= original_size:
                    break


            # --- PHASE 3: Final Output Write and Verification ---
            with open(original_path, 'wb') as output_file:
                 output_file.write(output_buffer)
            
            if decoded_count == original_size:
                return f"✅ SUCCESS: Decompressed {compressed_path} to {original_path}. Size: {decoded_count} bytes."
            else:
                 return f"❌ FAILURE: Decompression finished, but size mismatch. Expected {original_size}, Found {decoded_count}."
                         
    except Exception as e:
        return f"❌ FAILURE: An error occurred during decompression: {e}"

# --- MAIN EXECUTION BLOCK FOR TESTING ---

def main_lz77_test(input_filename="test_document_lz77.txt"):
    """
    Runs the compression and decompression pipeline for a test file.
    """
    # Create a large test file (32KB of repetitive data)
    TEST_FILE_PATH = input_filename
    TEST_CONTENT = b"The quick brown fox jumps over the lazy dog. " * 1000 + b"The quick brown fox jumps over the lazy dog. " * 2000
    
    if not os.path.exists(TEST_FILE_PATH):
        print(f"Creating test file: {TEST_FILE_PATH}")
        with open(TEST_FILE_PATH, 'wb') as f:
            f.write(TEST_CONTENT)
    
    # Define paths
    COMPRESSED_FILE_PATH = TEST_FILE_PATH + '.lz77'
    DECOMPRESSED_FILE_PATH = os.path.splitext(COMPRESSED_FILE_PATH)[0]

    # --- Step 1: COMPRESSION ---
    print("\n" + "="*50)
    compression_result = compress_lz77_file(TEST_FILE_PATH)
    print(compression_result)
    print("="*50)

    # --- Step 2: DECOMPRESSION ---
    if "SUCCESS" in compression_result and os.path.exists(COMPRESSED_FILE_PATH):
        print("\n[LZ77 DECOMPRESSION STARTED]")
        decompression_result = decompress_lz77_file(COMPRESSED_FILE_PATH)
        print(decompression_result)
        print("="*50)

        # --- Step 3: VERIFICATION ---
        if "SUCCESS" in decompression_result and os.path.exists(DECOMPRESSED_FILE_PATH):
            original_data = open(TEST_FILE_PATH, 'rb').read()
            decompressed_data = open(DECOMPRESSED_FILE_PATH, 'rb').read()
            
            print("\n[DATA INTEGRITY CHECK]")
            if original_data == decompressed_data:
                print("✅ VERIFICATION SUCCESS: Original and decompressed data match perfectly.")
            else:
                print("❌ VERIFICATION FAILURE: Data mismatch!")
        else:
            print("Verification skipped due to decompression failure.")
    else:
        print("Decompression skipped due to compression failure.")


if __name__ == '__main__':
    # You can comment out main_lz77_test() and call your compress/decompress functions directly 
    # with your specific file paths here for your actual testing.
    main_lz77_test('Sessional Activity sana.docx')