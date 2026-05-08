import cv2
from pathlib import Path

from ultralytics import YOLO

# Load a COCO-pretrained YOLOv8n model
model = YOLO("yolov8n.pt")

folder = Path("images")
if not folder.exists():
    print(f"Folder '{folder}' does not exist. Please create it and add 'imagen2.jpg'.")
    exit(1)
    
print(model.names)

# Run inference on all images
results = model('images/',
                classes=[2, 3, 5, 7],
    )

# Plot inference results
plot = results[0].plot()

# Save all images with detections
output_folder = Path("output")
output_folder.mkdir(exist_ok=True)
for i, result in enumerate(results):
    output_path = output_folder / f"detections_{i}.jpg"
    cv2.imwrite(str(output_path), result.plot())
    print(f"Saved detections to {output_path}")
