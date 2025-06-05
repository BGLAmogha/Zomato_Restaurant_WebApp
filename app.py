from flask import Flask, request, jsonify, render_template, redirect, url_for
from pymongo import MongoClient
from bson import ObjectId
import os
import io
import base64
import re
from PIL import Image
from werkzeug.utils import secure_filename
import google.generativeai as genai

app = Flask(__name__)

# Connect to MongoDB Compass
client = MongoClient("mongodb://localhost:27017/")
db = client["zomato"]
collection = db["zomato_collection"]

# Gemini API Configuration (Replace with your actual API key)
genai.configure(api_key="AIzaSyAsamV--_86q6nfaEEBjYE1SvHS9oCBcCc")

# Upload Folder Configuration
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    """Check if uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def detect_cuisine(image):
    """Detect cuisine type using the Gemini API."""
    model = genai.GenerativeModel('gemini-1.5-flash')

    # Convert image to base64
    img_byte_arr = io.BytesIO()
    if image.mode == "RGBA":
        image = image.convert("RGB")
    image.save(img_byte_arr, format='JPEG')
    img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

    # Send request to Gemini API
    response = model.generate_content([
        {"text": "Identify only the name of the cuisine in one or two words, e.g., 'Italian', 'Indian', 'Mexican', 'Desserts', 'Ice Cream'."},
        {"mime_type": "image/jpeg", "data": img_base64}
    ])
    try:
        print("🔍 Full Response from Gemini API:", response)
    except Exception as e:
        return "Unknown"
    if hasattr(response, 'text'):
        cuisine_detected = response.text.strip()
        
        # Extract only the first cuisine word using regex
        match = re.search(r"\b([A-Za-z\s]+)\b", cuisine_detected)
        if match:
            cuisine_cleaned = match.group(1).strip()
            print(f"✅ Extracted Cuisine: {cuisine_cleaned}")
            return cuisine_cleaned
    return "Unknown"

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/restaurant_details.html')
def restaurant_page():
    return render_template("restaurant_details.html")

@app.route("/restaurant/<restaurant_id>", methods=["GET"])
def get_restaurant_details(restaurant_id):
    try:
        if not ObjectId.is_valid(restaurant_id):
            return jsonify({"error": "Invalid restaurant ID"}), 400
        
        restaurant = collection.find_one({"_id": ObjectId(restaurant_id)}, {"_id": 0, "restaurant": 1})

        if restaurant:
            restaurant_data = restaurant.get("restaurant", {})

            return jsonify({
                "name": restaurant_data.get("name", "Unknown"),
                "cuisines": restaurant_data.get("cuisines", "Not Available"),
                "rating": restaurant_data.get("user_rating", {}).get("aggregate_rating", "N/A"),
                "address": restaurant_data.get("location", {}).get("address", "Address not available"),
                "latitude": restaurant_data.get("location", {}).get("latitude", ""),
                "longitude": restaurant_data.get("location", {}).get("longitude", ""),
                "image_url": restaurant_data.get("featured_image", "default_image.jpg"),
                "menu_url": restaurant_data.get("menu_url", "Not Available")
            }), 200
        
        return jsonify({"error": "Restaurant not found"}), 404

    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/restaurants', methods=['GET'])
def get_restaurants():
    try:
        page = int(request.args.get('page', 1))
        limit = 12
        skip = (page - 1) * limit

        search_query = request.args.get('search', "").strip()
        city_query = request.args.get('city', "").strip()

        query = {}

        if search_query:
            query["$or"] = [
                {"restaurant.name": {"$regex": search_query, "$options": "i"}},
                {"restaurant.cuisines": {"$regex": search_query, "$options": "i"}}
            ]

        if city_query:
            query["restaurant.location.city"] = {"$regex": city_query, "$options": "i"}

        restaurants_cursor = collection.find(query, {"_id": 1, "restaurant": 1}).skip(skip).limit(limit)

        result = []
        for r in restaurants_cursor:
            restaurant_data = r.get("restaurant", {})
            result.append({
                "id": str(r["_id"]),
                "name": restaurant_data.get("name", "Unknown"),
                "cuisines": restaurant_data.get("cuisines", "Not Available"),
                "rating": restaurant_data.get("user_rating", {}).get("aggregate_rating", "N/A"),
                "latitude": restaurant_data.get("location", {}).get("latitude", ""),
                "longitude": restaurant_data.get("location", {}).get("longitude", ""),
                "image_url": restaurant_data.get("featured_image", "default_image.jpg")
            })

        total_count = collection.count_documents(query)
        total_pages = (total_count + limit - 1) // limit

        return jsonify({
            "restaurants": result,
            "page": page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Image Search Route - Upload & Process Image
@app.route('/upload', methods=['POST'])
def upload_file():

    if 'image' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['image']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file format"}), 400

    # Convert file bytes to an image
    image = Image.open(io.BytesIO(file.read()))

    # Detect cuisine using Gemini API
    cuisine = detect_cuisine(image)

    # Find restaurants based on detected cuisine
    restaurants = list(collection.find({"restaurant.cuisines": {"$regex": cuisine, "$options": "i"}}))

    # Convert MongoDB cursor data into JSON-friendly format
    filtered_restaurants = []
    for r in restaurants:
        restaurant_data = r.get("restaurant", {})
        filtered_restaurants.append({
            "id": str(r["_id"]),
            "name": restaurant_data.get("name", "Unknown"),
            "cuisines": restaurant_data.get("cuisines", "Not Available"),
            "rating": restaurant_data.get("user_rating", {}).get("aggregate_rating", "N/A"),
            "latitude": restaurant_data.get("location", {}).get("latitude", ""),
            "longitude": restaurant_data.get("location", {}).get("longitude", ""),
            "image_url": restaurant_data.get("featured_image", "default_image.jpg")
        })

    return jsonify({
        "restaurants": filtered_restaurants,
        "cuisine": cuisine
    })

if __name__ == '__main__':
    app.run(debug=True)
