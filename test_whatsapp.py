import requests

print("Starting script...")

PHONE_NUMBER_ID = "1100478066474661"
ACCESS_TOKEN = "EAAaSogT1jCoBRODtq6m8Qvr4sCZCMHWxgbCevxITZAG9gUNTuoweD4PFBLr3ZB5HAM4OohXrZBwO4uLxRdrvAxEVyQyK6HLFAUHtzXZCViaHT0LIKZAiH1aZCXpQU5zuD3Xv3vHgmzJaSzZAYZA7RfiXvx9addxjOqVqiTZBTzrl7ZBZCRaUBGaXsfRuZAgIMbIT3xHNxsdkVyjaf2vhkyb3OJYakvZCmJZAvKlZAfJfKYZAZCYGGqojZAZBsjPPR2zGz4UnYAQh75wL5ZA2OajjvdZAHpz9SkXQIUnZA6BCwZDZD"

url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

data = {
    "messaging_product": "whatsapp",
    "to": "923314044494",  # your number
    "type": "template",
    "template": {
        "name": "template",
        "language": {
            "code": "en"
        }
    }
}

print("Sending request...")

response = requests.post(url, headers=headers, json=data)
print(response.json())

print("Response received!")
print("Status Code:", response.status_code)
print("Response Text:", response.text)