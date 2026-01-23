#!/bin/bash
# Test script using curl commands

BASE_URL="http://localhost:8000"

echo "=================================================="
echo "Question Translation API - cURL Tests"
echo "=================================================="

# Test 1: Health check
echo -e "\n[1] Health Check (GET /)"
curl -s "$BASE_URL/" | python3 -m json.tool

# Test 2: Get supported languages
echo -e "\n[2] Supported Languages (GET /languages)"
curl -s "$BASE_URL/languages" | python3 -m json.tool

# Test 3: API usage
echo -e "\n[3] API Usage (GET /usage)"
curl -s "$BASE_URL/usage" | python3 -m json.tool

# Test 4: Translate (requires a file)
# Uncomment and modify the path to test
# echo -e "\n[4] Translate File (POST /translate)"
# curl -X POST "$BASE_URL/translate" \
#   -F "file=@/path/to/your/questions.xlsx" \
#   -F "target_language=FR" \
#   -o translated_output.xlsx \
#   -w "\nHTTP Status: %{http_code}\n"

# Test 5: Translate info (returns JSON, no file)
# echo -e "\n[5] Translate Info (POST /translate/info)"
# curl -X POST "$BASE_URL/translate/info" \
#   -F "file=@/path/to/your/questions.xlsx" \
#   -F "target_language=FR" | python3 -m json.tool

echo -e "\n=================================================="
echo "Tests completed!"
echo ""
echo "To test translation, run:"
echo "  curl -X POST \"$BASE_URL/translate\" \\"
echo "    -F \"file=@your_file.xlsx\" \\"
echo "    -F \"target_language=FR\" \\"
echo "    -o translated.xlsx"
echo "=================================================="
