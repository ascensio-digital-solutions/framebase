import torch
from transformers import AutoFeatureExtractor, AutoModel
from PIL import Image
import numpy as np

device = "mps" if torch.backends.mps.is_available() else "cpu"
print("Device:", device)
model = AutoModel.from_pretrained("facebook/sscd-disc-mixup").to(device)
extractor = AutoFeatureExtractor.from_pretrained("facebook/sscd-disc-mixup")

img = Image.fromarray(np.zeros((224, 224, 3), dtype=np.uint8))
inputs = extractor(images=img, return_tensors="pt").to(device)
with torch.no_grad():
    out = model(**inputs)
    print(out.keys())
    # Try pooler output
    if hasattr(out, "pooler_output") and out.pooler_output is not None:
        emb = out.pooler_output
    else:
        # For ResNet it's often pooler_output or we take mean of last_hidden_state
        emb = out.last_hidden_state.mean(dim=[2, 3])
    print(emb.shape)
