# List of models for the command /model
models = {
    "default": {
        "name": "DreamShaper XL (Lightning)",
        "checkpoint": "dreamshaperXL_lightningDPMSDE.safetensors",
        "clip_skip": 2,
        "sampler": "DPM++ SDE",
        "scheduler": "Karras",
        "cfg_scale": 2,
        "steps": 6,
        "width": 1024,
        "height": 1024
    },
    "model_1": {
        "name": "Juggernaut XL (XI)",
        "checkpoint": "juggernautXL_juggXIByRundiffusion.safetensors",
        "clip_skip": 2,
        "sampler": "DPM++ 2M SDE",
        "scheduler": "Karras",
        "cfg_scale": 4.5,
        "steps": 30,
        "width": 1024,
        "height": 1024
    },
    "model_2": {
        "name": "Prefect Pony XL (v4.0)",
        "checkpoint": "prefectPonyXL_v40.safetensors",
        "clip_skip": 2,
        "sampler": "DPM++ 2M",
        "scheduler": "Karras",
        "cfg_scale": 7.0,
        "steps": 25,
        "width": 1024,
        "height": 1024
    },
}