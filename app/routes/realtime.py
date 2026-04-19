from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi import HTTPException, status
from app.security import require_roles

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: Dict[str, List[WebSocket]] = {}

    async def connect(self, room: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.rooms.setdefault(room, []).append(websocket)

    def disconnect(self, room: str, websocket: WebSocket) -> None:
        conns = self.rooms.get(room, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns and room in self.rooms:
            self.rooms.pop(room, None)

    async def broadcast(self, room: str, message: dict) -> None:
        for ws in list(self.rooms.get(room, [])):
            try:
                await ws.send_json(message)
            except Exception:
                # Drop broken connections
                self.disconnect(room, ws)


manager = ConnectionManager()


@router.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    await manager.connect(room, websocket)
    try:
        while True:
            # Echo ping/pong or client messages if needed
            _ = await websocket.receive_text()
            await websocket.send_json({"type": "ack"})
    except WebSocketDisconnect:
        manager.disconnect(room, websocket)


@router.post("/notify/{room}")
async def notify_room(room: str, payload: dict, _=Depends(require_roles("doctor", "receptionist", "admin"))):
    try:
        await manager.broadcast(room, {"type": "event", "data": payload})
        return {"success": True}
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to notify room")
