
"""
Quick test script to verify WhatsApp message sending works
"""
from app.services.whatsapp_service import send_queue_message

# Test data - REPLACE WITH YOUR ACTUAL DATA
TEST_PHONE = "+923001234567"  # Your phone number with country code
TEST_NAME = "Test Patient"
TEST_POSITION = 15
TEST_WAIT_TIME = 45
TEST_DOCTOR = "Dr. Test Doctor"
TEST_HOSPITAL = "Test Hospital"
TEST_ROOM = "Room 1"

print("=" * 60)
print("Testing WhatsApp Message Sending")
print("=" * 60)
print(f"\nSending test message to: {TEST_PHONE}")
print(f"Doctor: {TEST_DOCTOR}")
print(f"Hospital: {TEST_HOSPITAL}")
print(f"Token Position: {TEST_POSITION}")
print(f"Wait Time: {TEST_WAIT_TIME} minutes\n")

try:
    message_sid = send_queue_message(
        phone=TEST_PHONE,
        name=TEST_NAME,
        position=TEST_POSITION,
        wait_time=TEST_WAIT_TIME,
        doctor_name=TEST_DOCTOR,
        hospital_name=TEST_HOSPITAL,
        room_number=TEST_ROOM
    )
    
    if message_sid:
        print(f"✅ SUCCESS! Message sent with SID: {message_sid}")
    else:
        print("❌ FAILED! Message was not sent (returned None)")
        print("\nPossible reasons:")
        print("1. Phone number is None or empty")
        print("2. Twilio credentials not configured")
        print("3. Error occurred during sending (check logs)")
        
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test Complete")
print("=" * 60)
