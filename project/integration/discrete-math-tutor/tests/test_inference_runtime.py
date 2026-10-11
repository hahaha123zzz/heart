"""检查设备配置和静默 CPU 回退。"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from knowledge.inference_runtime import configured_device, prepare_onnx, verify_device

class RuntimeTests(unittest.TestCase):
    def test_invalid_device_rejected(self):
        with patch.dict(os.environ, {"RAG_RERANK_DEVICE": "cdua"}):
            with self.assertRaises(ValueError):
                configured_device("RERANK")
    def test_cpu_is_explicit(self):
        self.assertEqual(prepare_onnx("cpu")["providers"], ["CPUExecutionProvider"])
    def test_cuda_request_rejects_cpu_only_session(self):
        m = SimpleNamespace(model=SimpleNamespace(model=SimpleNamespace(
            get_providers=lambda: ["CPUExecutionProvider"])))
        with self.assertRaises(RuntimeError):
            verify_device(m, "cuda")
        verify_device(m, "cpu")

    def test_explicit_cache_is_initialized_before_cuda_preload(self):
        fake=SimpleNamespace(get_available_providers=lambda:['CUDAExecutionProvider'],preload_dlls=lambda **kwargs:self.assertTrue(bool(os.environ.get('CUDA_CACHE_PATH'))))
        with patch.dict(os.environ,{},clear=True), patch.dict('sys.modules',{'onnxruntime':fake}), patch('knowledge.inference_runtime.Path.mkdir') as mkdir:
            prepare_onnx('cuda')
            self.assertTrue(os.environ['CUDA_CACHE_PATH'].endswith('cuda'))
            mkdir.assert_called_once()
    def test_user_cache_configuration_is_preserved(self):
        fake=SimpleNamespace(get_available_providers=lambda:['CUDAExecutionProvider'],preload_dlls=lambda **kwargs:None)
        with patch.dict(os.environ,{'CUDA_CACHE_PATH':'configured-cache','CUDA_CACHE_DISABLE':'1'}), patch.dict('sys.modules',{'onnxruntime':fake}), patch('knowledge.inference_runtime.Path.mkdir') as mkdir:
            prepare_onnx('cuda')
            self.assertEqual(os.environ['CUDA_CACHE_PATH'],'configured-cache')
            self.assertEqual(os.environ['CUDA_CACHE_DISABLE'],'1')
            mkdir.assert_not_called()
