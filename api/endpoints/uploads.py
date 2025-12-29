"""REST endpoints for image uploads.
These endpoints only upload images and return the path + presigned URL.
The actual data persistence happens via GraphQL mutations.
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from bson import ObjectId
import time

from utils.auth import get_current_user_id_from_header
from utils.s3 import upload_file, generate_presigned_url
from services.image_processing import process_image_for_store, process_product_image

router = APIRouter(prefix="/upload", tags=["Uploads"])


@router.post("/business/avatar", status_code=status.HTTP_200_OK)
async def upload_business_avatar(
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload avatar image for a business.
    Image will be converted to JPG, resized to 400x400, and compressed.
    Returns the image path to be used in GraphQL mutation.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Read and process image
    file_content = await image.read()
    try:
        processed_content, extension = process_image_for_store(
            file_content,
            "business_avatar",
            convert_to_jpg=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")

    # Generate unique ID for the image
    entity_id = str(ObjectId())

    # Upload image
    try:
        image_path = await upload_file(processed_content, "businesses/avatars", entity_id, extension)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    return {
        "image_path": image_path,
        "image_url": generate_presigned_url(image_path)
    }


@router.post("/business/cover", status_code=status.HTTP_200_OK)
async def upload_business_cover(
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload cover image for a business.
    Image will be converted to JPG, resized to 1200x400, and compressed.
    Returns the image path to be used in GraphQL mutation.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Read and process image
    file_content = await image.read()
    try:
        processed_content, extension = process_image_for_store(
            file_content,
            "business_cover",
            convert_to_jpg=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")

    # Generate unique ID for the image
    entity_id = str(ObjectId())

    # Upload image
    try:
        image_path = await upload_file(processed_content, "businesses/covers", entity_id, extension)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    return {
        "image_path": image_path,
        "image_url": generate_presigned_url(image_path)
    }


@router.post("/branch/avatar", status_code=status.HTTP_200_OK)
async def upload_branch_avatar(
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload avatar image for a branch.
    Image will be converted to JPG, resized to 400x400, and compressed.
    Returns the image path to be used in GraphQL mutation.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Read and process image
    file_content = await image.read()
    try:
        processed_content, extension = process_image_for_store(
            file_content,
            "branch_avatar",
            convert_to_jpg=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")

    # Generate unique ID for the image
    entity_id = str(ObjectId())

    # Upload image
    try:
        image_path = await upload_file(processed_content, "branches/avatars", entity_id, extension)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    return {
        "image_path": image_path,
        "image_url": generate_presigned_url(image_path)
    }


@router.post("/branch/cover", status_code=status.HTTP_200_OK)
async def upload_branch_cover(
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload cover image for a branch.
    Image will be converted to JPG, resized to 1200x400, and compressed.
    Returns the image path to be used in GraphQL mutation.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Read and process image
    file_content = await image.read()
    try:
        processed_content, extension = process_image_for_store(
            file_content,
            "branch_cover",
            convert_to_jpg=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")

    # Generate unique ID for the image
    entity_id = str(ObjectId())

    # Upload image
    try:
        image_path = await upload_file(processed_content, "branches/covers", entity_id, extension)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    return {
        "image_path": image_path,
        "image_url": generate_presigned_url(image_path)
    }


@router.post("/product/image", status_code=status.HTTP_200_OK)
async def upload_product_image(
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload image for a product.
    Image is optimized but preserves transparency (not converted to JPG).
    Returns the image path to be used in GraphQL mutation.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Read and process image
    file_content = await image.read()
    filename = image.filename or "image.png"
    original_ext = "." + filename.split(".")[-1] if "." in filename else ".png"

    try:
        processed_content, extension = process_product_image(file_content, original_ext)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")

    # Generate unique ID for the image
    entity_id = str(ObjectId())

    # Upload image
    try:
        image_path = await upload_file(processed_content, "products", entity_id, extension)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    return {
        "image_path": image_path,
        "image_url": generate_presigned_url(image_path)
    }


@router.post("/user/avatar", status_code=status.HTTP_200_OK)
async def upload_user_avatar(
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload avatar image for a user.
    Image will be converted to JPG, resized to 400x400, and compressed.
    Returns the image path to be used in GraphQL mutation.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Read and process image
    file_content = await image.read()
    try:
        processed_content, extension = process_image_for_store(
            file_content,
            "user_avatar",
            convert_to_jpg=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")

    # Use user_id as entity_id for the image
    entity_id = user_id

    # Upload image
    try:
        image_path = await upload_file(processed_content, "users/avatars", entity_id, extension)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    return {
        "image_path": image_path,
        "image_url": generate_presigned_url(image_path)
    }
