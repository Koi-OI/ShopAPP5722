from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from db.mongo import db
from typing import List
from utils.auth import get_current_user
from bson import ObjectId

router = APIRouter()



class Message(BaseModel):
    user_id: str
    username: str
    content: str
    timestamp: str


# Response Model (可以根据需求修改)
class CreateChatRoomResponse(BaseModel):
    status: str
    data: dict

@router.post("/api/v1/chatrooms/{seller_id}")
async def create_chatroom(seller_id: str, user: dict = Depends(get_current_user)):
    """
    Create a new chatroom between user and seller.
    """
    # Validate if the user and seller are different (a user cannot create a chatroom with themselves)
    if user["user_id"] == seller_id:
        raise HTTPException(status_code=400, detail="User cannot create a chatroom with themselves.")

    # Check if a chatroom already exists between the user and the seller
    existing_chatroom = await db["chatrooms"].find_one({"user_id": user["user_id"], "seller_id": seller_id})
    if existing_chatroom:
        raise HTTPException(status_code=400, detail="Chatroom already exists between this user and seller.")

    # Create the new chatroom data
    chatroom_data = {
        "user_id": user["user_id"],
        "seller_id": seller_id,
        "created_at": datetime.utcnow().isoformat()
    }

    # Insert the chatroom into the database
    result = await db["chatrooms"].insert_one(chatroom_data)

    # Return the generated chatroom_id (MongoDB's _id as chatroom_id)
    return {
        "status": "OK",
        "data": {
            "chatroom_id": str(result.inserted_id),
            "message": "Chatroom created successfully"
        }
    }


@router.get("/api/v1/chatrooms/{chatroom_id}/messages", response_model=List[Message])
async def get_messages(chatroom_id: str, user: dict = Depends(get_current_user)):
    """
    Get all messages in a specific chatroom.
    Ensure the user is part of the chatroom before retrieving messages.
    """
    # Check if the chatroom exists and if the user is part of it
    chatroom = await db["chatrooms"].find_one({"_id": ObjectId(chatroom_id), "$or": [{"user_id": user["user_id"]}, {"seller_id": user["user_id"]}]})

    if not chatroom:
        raise HTTPException(status_code=404, detail="Chatroom not found or you are not part of this chatroom")

    # Fetch messages from the chatroom
    messages = await db["messages"].find({"chatroom_id": chatroom_id}).to_list(length=100)
    if not messages:
        raise HTTPException(status_code=404, detail="No messages found in this chatroom")

    return [{"user_id": message["user_id"],
             "username": message["username"],
             "content": message["content"],
             "timestamp": message["timestamp"]} for message in messages]


@router.post("/api/v1/chatrooms/{chatroom_id}/messages")
async def send_message(chatroom_id: str, message: Message, user: dict = Depends(get_current_user)):
    """
    Send a message to a specific chatroom.
    Ensure the user is part of the chatroom before sending a message.
    """
    # Check if the chatroom exists and if the user is part of it
    chatroom = await db["chatrooms"].find_one({"_id": ObjectId(chatroom_id), "$or": [{"user_id": user["user_id"]}, {"seller_id": user["user_id"]}]})
    
    if not chatroom:
        raise HTTPException(status_code=404, detail="Chatroom not found or you are not part of this chatroom")

    # Store the user's message
    user_message = {
        "chatroom_id": chatroom_id,
        "user_id": user["user_id"],
        "username": user["username"],
        "content": message.content,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Insert user's message into the messages collection
    await db["messages"].insert_one(user_message)

    # Automatically send a reply from the seller (hardcoded)
    seller_reply = {
        "chatroom_id": chatroom_id,
        "user_id": chatroom["seller_id"],
        "username": "Seller",  # This can be a hardcoded seller username for now
        "content": "Thank you for your message. We will get back to you shortly.",
        "timestamp": datetime.utcnow().isoformat()
    }

    # Insert seller's reply into the messages collection
    await db["messages"].insert_one(seller_reply)

    return {"status": "OK", "data": {"message": "Message sent successfully"}}

class ChatroomResponse(BaseModel):
    chatroom_id: str
    seller_name: str
    seller_avatar: str

@router.get("/api/v1/chatrooms", response_model=dict)
async def get_user_chatrooms(user: dict = Depends(get_current_user)):
    """
    Get all chatrooms for the current user
    """
    user_id = user["user_id"]

    chatrooms = await db["chatrooms"].find({"user_id": user_id}).to_list(100)

    if not chatrooms:
        raise HTTPException(status_code=404, detail="No chatrooms found for this user")

    chatroom_responses = []

    # 遍历每个聊天室，获取商家的头像和名称
    for chatroom in chatrooms:
        seller_id = chatroom["seller_id"]
        
        # 查找商家信息
        seller = await db["sellers"].find_one({"seller_id": seller_id})
        if seller:
            chatroom_responses.append(ChatroomResponse(
                chatroom_id=str(chatroom["_id"]),
                seller_name=seller.get("name", "Unknown"),
                seller_avatar=seller.get("image", "")
            ))

    return {
        "status": "OK",
        "data": {
            "chatrooms": chatroom_responses
        }
    }