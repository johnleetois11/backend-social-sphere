from fastapi import APIRouter, Depends, HTTPException

from app.schemas.profile import ProfileUpdate, PasswordChange
from app.services import profile_service
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/me")
async def get_my_profile(user=Depends(get_current_mongo_user)):
    profile = await profile_service.get_own_profile(str(user["_id"]))
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@router.put("/me")
async def update_my_profile(
    data: ProfileUpdate,
    user=Depends(get_current_mongo_user),
):
    return await profile_service.update_profile(str(user["_id"]), data)


@router.put("/me/password")
async def change_password(
    data: PasswordChange,
    user=Depends(get_current_mongo_user),
):
    await profile_service.change_password(
        str(user["_id"]),
        data.current_password,
        data.new_password,
    )
    return {"message": "Password changed successfully"}


@router.delete("/me")
async def delete_my_account(user=Depends(get_current_mongo_user)):
    await profile_service.delete_account(str(user["_id"]))
    return {"message": "Account deleted"}


@router.get("/me/activity")
async def get_activity(user=Depends(get_current_mongo_user)):
    return await profile_service.get_login_activity(str(user["_id"]))


@router.get("/me/groups-stats")
async def get_group_stats(user=Depends(get_current_mongo_user)):
    return await profile_service.get_my_group_stats(str(user["_id"]))


@router.get("/{user_id}/group/{group_id}")
async def get_member_profile(
    user_id: str,
    group_id: str,
    viewer=Depends(get_current_mongo_user),
):
    return await profile_service.get_member_profile(
        str(viewer["_id"]),
        user_id,
        group_id,
    )