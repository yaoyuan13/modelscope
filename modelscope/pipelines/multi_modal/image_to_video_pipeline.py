# Copyright (c) Alibaba, Inc. and its affiliates.

import os
import tempfile
from typing import Any, Dict, Optional

import cv2
import torch
from einops import rearrange

from modelscope.metainfo import Pipelines
from modelscope.outputs import OutputKeys
from modelscope.pipelines.base import Input, Model, Pipeline
from modelscope.pipelines.builder import PIPELINES
from modelscope.preprocessors.image import LoadImage
from modelscope.utils.constant import Tasks
from modelscope.utils.logger import get_logger

logger = get_logger()


@PIPELINES.register_module(
    Tasks.image_to_video, module_name=Pipelines.image_to_video_task_pipeline)
class ImageToVideoPipeline(Pipeline):
    r""" Image To Video Pipeline.

    Examples:
    >>> from modelscope.pipelines import pipeline
    >>> from modelscope.outputs import OutputKeys

    >>> p = pipeline('image-to-video', 'damo/Image-to-Video')
    >>> input = 'path_to_image'
    >>> p(input,)

    >>>  {OutputKeys.OUTPUT_VIDEO: path-to-the-generated-video}
    >>>
    """

    def __init__(self, model: str, **kwargs):
        """
        use `model` to create a kws pipeline for prediction
        Args:
            model: model id on modelscope hub.
        """
        super().__init__(model=model, **kwargs)

    def preprocess(self, input: Input, **preprocess_params) -> Dict[str, Any]:
        img_path = input

        image = LoadImage.convert_to_img(img_path)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        vit_frame = self.model.vid_trans(image)
        vit_frame = vit_frame.unsqueeze(0)
        vit_frame = vit_frame.to(self.model.device)

        return {'vit_frame': vit_frame}

    def forward(self, input: Dict[str, Any],
                **forward_params) -> Dict[str, Any]:
        video = self.model(input)
        return {'video': video}

    def postprocess(self, inputs: Dict[str, Any],
                    **post_params) -> Dict[str, Any]:
        video = tensor2vid(inputs['video'], self.model.cfg.mean,
                           self.model.cfg.std)
        output_video_path = post_params.get('output_video', None)
        temp_video_file = False
        if output_video_path is None:
            output_video_path = tempfile.NamedTemporaryFile(suffix='.mp4').name
            temp_video_file = True

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        h, w, c = video[0].shape
        video_writer = cv2.VideoWriter(
            output_video_path, fourcc, fps=8, frameSize=(w, h))
        for i in range(len(video)):
            img = cv2.cvtColor(video[i], cv2.COLOR_RGB2BGR)
            video_writer.write(img)
        video_writer.release()
        if temp_video_file:
            video_file_content = b''
            with open(output_video_path, 'rb') as f:
                video_file_content = f.read()
            os.remove(output_video_path)
            return {OutputKeys.OUTPUT_VIDEO: video_file_content}
        else:
            return {OutputKeys.OUTPUT_VIDEO: output_video_path}


def tensor2vid(video, mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]):
    mean = torch.tensor(mean, device=video.device).reshape(1, -1, 1, 1, 1)
    std = torch.tensor(std, device=video.device).reshape(1, -1, 1, 1, 1)

    video = video.mul_(std).add_(mean)
    video.clamp_(0, 1)
    video = video * 255.0

    images = rearrange(video, 'b c f h w -> b f h w c')[0]
    images = [(img.numpy()).astype('uint8') for img in images]

    return images
