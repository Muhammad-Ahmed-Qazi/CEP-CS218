import os
import traceback
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from flask_cors import CORS
from Image_Compression import compress_image
from Audio_Compression import compress_audio
from Pdf_Compression import compress_file, decompress_file



from werkzeug.utils import secure_filename

# -----------------------------------------------------------
# PATH CONFIGURATION
# -----------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_DIR = os.path.join(DATA_DIR, "users")
USER_DATA_FILE = os.path.join(DATA_DIR, "users.txt")

os.makedirs(USERS_DIR, exist_ok=True)
if not os.path.exists(USER_DATA_FILE):
    open(USER_DATA_FILE, "w").close()

# -----------------------------------------------------------
# FLASK APP SETUP
# -----------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "supersecretkey"  # ⚠️ change in production
CORS(app)

# -----------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------
def find_user(email):
    try:
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                stored_email, stored_password, stored_username = line.strip().split(",", 2)
                if stored_email == email:
                    return {
                        "email": stored_email,
                        "password": stored_password,
                        "username": stored_username,
                    }
    except Exception as e:
        print(f"Error reading users.txt: {e}")
    return None


def create_user(username, email, password):
    try:
        with open(USER_DATA_FILE, "a", encoding="utf-8") as f:
            f.write(f"{email},{password},{username}\n")

        # Create user-specific folders
        user_root = os.path.join(USERS_DIR, email)
        os.makedirs(os.path.join(user_root, "image/original"), exist_ok=True)
        os.makedirs(os.path.join(user_root, "image/compressed"), exist_ok=True)
        os.makedirs(os.path.join(user_root, "audio"), exist_ok=True)
        os.makedirs(os.path.join(user_root, "pdf"), exist_ok=True)

        print(f"✅ User created: {email}")
        return True
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return False

# -----------------------------------------------------------
# DECORATOR: LOGIN REQUIRED
# -----------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper

# -----------------------------------------------------------
# ROUTES
# -----------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html", user=session.get("user"))

@app.route("/signup")
def signup_page():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("signup.html", user=session.get("user"))

@app.route("/login")
def login_page():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html", user=session.get("user"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = session.get("user")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("dashboard.html", username=user["username"], user=user)

@app.context_processor
def inject_user():
    return dict(user=session.get("user"))

# -----------------------------------------------------------
# IMAGE COMPRESSION ROUTES
# -----------------------------------------------------------
@app.route("/image-compress")
@login_required
def image_compress():
    return render_template("image_compress.html", user=session.get("user"))

@app.route("/compress_image", methods=["POST"])
@login_required
def compress_image_route():
    try:
        user = session.get("user")
        file = request.files.get("image")
        quality = int(request.form.get("quality", 70))

        if not file:
            return jsonify({"error": "No file uploaded"}), 400

        filename = secure_filename(file.filename)
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext not in ["jpg", "jpeg", "png", "webp"]:
            return jsonify({"error": "Invalid file type"}), 400

        # Ensure directories exist
        user_dir = os.path.join(USERS_DIR, user["email"], "image")
        original_dir = os.path.join(user_dir, "original")
        compressed_dir = os.path.join(user_dir, "compressed")
        os.makedirs(original_dir, exist_ok=True)
        os.makedirs(compressed_dir, exist_ok=True)

        input_path = os.path.join(original_dir, filename)
        output_path = os.path.join(compressed_dir, filename)
        file.save(input_path)

        # Run compression
        success = compress_image(input_path, output_path, quality)
        if not success or not os.path.exists(output_path):
            return jsonify({"error": "Compression failed"}), 500

        # Compute sizes
        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(output_path)
        saved = original_size - compressed_size
        saved_percent = saved / original_size * 100 if original_size != 0 else 0

        return jsonify({
            "success": True,
            "filename": filename,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "saved": saved,
            "saved_percent": round(saved_percent, 2),
            "download_url": f"/download_compressed/{filename}"
        })

    except Exception as e:
        print("Error in /compress_image:", e)
        traceback.print_exc()
        return jsonify({"error": "Internal Server Error"}), 500

@app.route("/download_audio/<filename>")
@login_required
def download_audio(filename):
    path = session.get("last_audio_path")
    if not path or not os.path.exists(path):
        return "File not found", 404
    return send_file(path, as_attachment=True)


@app.route("/download_pdf/<filename>")
@login_required
def download_pdf(filename):
    user = session.get("user")
    pdf_dir = os.path.join(USERS_DIR, user["email"], "pdf")
    file_path = os.path.join(pdf_dir, filename)

    if not os.path.exists(file_path):
        return "File not found", 404

    return send_file(file_path, as_attachment=True)


@app.route("/compress_audio", methods=["POST"])
@login_required
def compress_audio_route():
    user = session.get("user")
    file = request.files.get("audio")
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ["wav", "mp3", "flac"]:
        return jsonify({"success": False, "error": "Unsupported file type"}), 400

    user_dir = os.path.join(USERS_DIR, user["email"], "audio")
    os.makedirs(user_dir, exist_ok=True)

    input_path = os.path.join(user_dir, filename)
    output_path = os.path.join(user_dir, f"compressed_{filename}")
    file.save(input_path)

    result = compress_audio(input_path, output_path)
    if not result["success"]:
        return jsonify(result), 500

    result["download_url"] = url_for("download_audio", filename=f"compressed_{filename}")
    session["last_audio_path"] = output_path  # store it temporarily
    return jsonify(result)

@app.route("/compress_file", methods=["POST"])
@login_required
def compress_file_route():
    try:
        user = session.get("user")
        file = request.files.get("file")

        if not file:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        filename = secure_filename(file.filename)
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext not in ["pdf", "txt"]:
            return jsonify({"success": False, "error": "Only PDF and TXT files allowed"}), 400

        # Save original file
        user_dir = os.path.join(USERS_DIR, user["email"], "pdf")
        os.makedirs(user_dir, exist_ok=True)
        input_path = os.path.join(user_dir, filename)
        file.save(input_path)

        # Compress file using Huffman algorithm
        compressed_filename = f"{filename}.huff"
        compressed_path = os.path.join(user_dir, compressed_filename)
        compress_file(input_path, compressed_path)

        # Decompress back to original format for download (optional)
        decompressed_filename = f"{filename.rsplit('.',1)[0]}_decompressed.{ext}"
        decompressed_path = os.path.join(user_dir, decompressed_filename)
        decompress_file(compressed_path, decompressed_path)

        # File size stats
        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(compressed_path)
        saved = original_size - compressed_size
        saved_percent = round(saved / original_size * 100, 2) if original_size else 0

        # Return JSON response
        return jsonify({
            "success": True,
            "filename": filename,
            "compressed_filename": compressed_filename,
            "decompressed_filename": decompressed_filename,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "saved": saved,
            "saved_percent": saved_percent,
            "download_compressed_url": url_for("download_compressed_file", filename=compressed_filename),
            "download_decompressed_url": url_for("download_pdf", filename=decompressed_filename)
        })

    except Exception as e:
        print("Error in /compress_file:", e)
        traceback.print_exc()
        return jsonify({"success": False, "error": "Internal server error"}), 500







@app.route("/decompress_file", methods=["POST"])
@login_required
def decompress_file_route():
    try:
        user = session.get("user")
        file = request.files.get("file")

        if not file:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        filename = secure_filename(file.filename)
        if not filename.endswith(".huff"):
            return jsonify({"success": False, "error": "Invalid file type"}), 400

        user_dir = os.path.join(USERS_DIR, user["email"], "pdf")
        os.makedirs(user_dir, exist_ok=True)

        input_path = os.path.join(user_dir, filename)
        file.save(input_path)

        base_name = filename[:-5]  # remove ".huff"
        ext = "pdf" if base_name.lower().endswith(".pdf") else "txt"
        output_filename = f"{base_name}"  # keep original filename
        output_path = os.path.join(user_dir, output_filename)

        # Perform actual decompression
        decompress_file(input_path, output_path)

        # Return download URL pointing to original format file
        return jsonify({
            "success": True,
            "original_huff": filename,
            "decompressed_file": output_filename,
            "download_url": url_for("download_pdf", filename=output_filename)
        })

    except Exception as e:
        print("Error in /decompress_file:", e)
        traceback.print_exc()
        return jsonify({"success": False, "error": "Internal server error"}), 500


@app.route("/download_compressed_file/<filename>")
@login_required
def download_compressed_file(filename):
    user = session.get("user")
    pdf_dir = os.path.join(USERS_DIR, user["email"], "pdf")
    file_path = os.path.join(pdf_dir, filename)

    if not os.path.exists(file_path):
        return "File not found", 404

    # Determine MIME type
    if filename.lower().endswith(".pdf.huff"):
        mimetype = "application/octet-stream"
    elif filename.lower().endswith(".txt.huff"):
        mimetype = "application/octet-stream"
    else:
        mimetype = "application/octet-stream"

    return send_file(file_path, as_attachment=True, download_name=filename, mimetype=mimetype)







@app.route("/download_decompressed/<filename>")
@login_required
def download_decompressed(filename):
    user = session.get("user")
    pdf_dir = os.path.join(USERS_DIR, user["email"], "pdf")
    input_path = os.path.join(pdf_dir, filename)

    if not os.path.exists(input_path):
        return "File not found", 404

    # Determine output filename
    if filename.lower().endswith(".pdf.huff"):
        output_filename = filename.replace(".huff", "_decompressed.pdf")
        mimetype = "application/pdf"
    elif filename.lower().endswith(".txt.huff"):
        output_filename = filename.replace(".huff", "_decompressed.txt")
        mimetype = "text/plain"
    else:
        output_filename = filename.replace(".huff", "_decompressed.bin")
        mimetype = "application/octet-stream"

    output_path = os.path.join(pdf_dir, output_filename)

    # Make sure directories exist
    os.makedirs(pdf_dir, exist_ok=True)

    # Decompress only if the file doesn't exist yet
    if not os.path.exists(output_path):
        try:
            decompress_file(input_path, output_path)
        except Exception as e:
            print("Error decompressing file:", e)
            return "Decompression failed", 500

    # Serve decompressed file
    return send_file(
        output_path,
        as_attachment=True,
        download_name=output_filename,
        mimetype=mimetype
    )


# -----------------------------------------------------------
# AUDIO & PDF ROUTES
# -----------------------------------------------------------
@app.route("/audio-compress")
@login_required
def audio_compress():
    return render_template("audio_compress.html", user=session.get("user"))


@app.route("/pdf-compress")
@login_required
def pdf_compress():
    return render_template("file_compress.html", user=session.get("user"))

# -----------------------------------------------------------
# AUTH API ROUTES
# -----------------------------------------------------------
@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not all([username, email, password]):
        return jsonify({"success": False, "error": "All fields are required"}), 400

    if find_user(email):
        return jsonify({"success": False, "error": "Email already registered"}), 409

    if not create_user(username, email, password):
        return jsonify({"success": False, "error": "User creation failed"}), 500

    session["user"] = {"username": username, "email": email}
    return jsonify({"success": True, "username": username})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = find_user(email)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404
    if user["password"] != password:
        return jsonify({"success": False, "error": "Incorrect password"}), 401

    session["user"] = {"username": user["username"], "email": user["email"]}
    return jsonify({"success": True, "username": user["username"]})

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("home"))

# -----------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
