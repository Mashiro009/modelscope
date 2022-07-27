from typing import Any, Dict

import cv2
import numpy as np
import PIL
import torch

from modelscope.metainfo import Pipelines
from modelscope.outputs import OutputKeys
from modelscope.pipelines.base import Input
from modelscope.preprocessors import load_image
from modelscope.utils.constant import Tasks
from modelscope.utils.logger import get_logger
from ..base import Pipeline
from ..builder import PIPELINES

logger = get_logger()


@PIPELINES.register_module(
    Tasks.image_classification_imagenet,
    module_name=Pipelines.general_image_classification)
@PIPELINES.register_module(
    Tasks.image_classification_dailylife,
    module_name=Pipelines.daily_image_classification)
class GeneralImageClassificationPipeline(Pipeline):

    def __init__(self, model: str, **kwargs):
        """
        use `model` and `preprocessor` to create a kws pipeline for prediction
        Args:
            model: model id on modelscope hub.
        """
        super().__init__(model=model, **kwargs)

        logger.info('load model done')

    def preprocess(self, input: Input) -> Dict[str, Any]:
        from mmcls.datasets.pipelines import Compose
        from mmcv.parallel import collate, scatter
        if isinstance(input, str):
            img = np.array(load_image(input))
        elif isinstance(input, PIL.Image.Image):
            img = np.array(input.convert('RGB'))
        elif isinstance(input, np.ndarray):
            if len(input.shape) == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            img = input[:, :, ::-1]  # in rgb order
        else:
            raise TypeError(f'input should be either str, PIL.Image,'
                            f' np.array, but got {type(input)}')

        mmcls_cfg = self.model.cfg
        # build the data pipeline
        if mmcls_cfg.data.test.pipeline[0]['type'] == 'LoadImageFromFile':
            mmcls_cfg.data.test.pipeline.pop(0)
        data = dict(img=img)
        test_pipeline = Compose(mmcls_cfg.data.test.pipeline)
        data = test_pipeline(data)
        data = collate([data], samples_per_gpu=1)
        if next(self.model.parameters()).is_cuda:
            # scatter to specified GPU
            data = scatter(data, [next(self.model.parameters()).device])[0]

        return data

    def forward(self, input: Dict[str, Any]) -> Dict[str, Any]:

        with torch.no_grad():
            input['return_loss'] = False
            scores = self.model(input)

        return {'scores': scores}

    def postprocess(self, inputs: Dict[str, Any]) -> Dict[str, Any]:

        scores = inputs['scores']
        pred_score = np.max(scores, axis=1)[0]
        pred_label = np.argmax(scores, axis=1)[0]
        result = {'pred_label': pred_label, 'pred_score': float(pred_score)}
        result['pred_class'] = self.model.CLASSES[result['pred_label']]

        outputs = {
            OutputKeys.SCORES: [result['pred_score']],
            OutputKeys.LABELS: [result['pred_class']]
        }
        return outputs
