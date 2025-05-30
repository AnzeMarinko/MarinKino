import cv2
import numpy as np
import os
import torch
from tqdm import tqdm
from torch import nn as nn
import ffmpeg

from .utils import RealESRGANer


def get_video_meta_info(video_path):
    ret = {}
    probe = ffmpeg.probe(video_path)
    video_streams = [stream for stream in probe['streams'] if stream['codec_type'] == 'video']
    has_audio = any(stream['codec_type'] == 'audio' for stream in probe['streams'])
    ret['width'] = video_streams[0]['width']
    ret['height'] = video_streams[0]['height']
    ret['fps'] = eval(video_streams[0]['avg_frame_rate'])
    ret['audio'] = ffmpeg.input(video_path).audio if has_audio else None
    ret['nb_frames'] = int(video_streams[0]['nb_frames'])
    return ret


class Reader:

    def __init__(self, input_video_path):
        self.paths = []  # for image&folder type
        self.audio = None
        self.input_fps = 24
        self.stream_reader = (
            ffmpeg.input(input_video_path).output('pipe:', format='rawvideo', pix_fmt='bgr24',
                                            loglevel='error').run_async(
                                                pipe_stdin=True, pipe_stdout=True, cmd="ffmpeg"))
        meta = get_video_meta_info(input_video_path)
        self.width = meta['width']
        self.height = meta['height']
        self.input_fps = meta['fps']
        self.audio = meta['audio']
        self.nb_frames = meta['nb_frames']
        self.idx = 0

    def get_resolution(self):
        return self.height, self.width

    def get_audio(self):
        return self.audio

    def __len__(self):
        return self.nb_frames

    def get_frame(self):
        img_bytes = self.stream_reader.stdout.read(self.width * self.height * 3)  # 3 bytes for one pixel
        if not img_bytes:
            return None
        img = np.frombuffer(img_bytes, np.uint8).reshape([self.height, self.width, 3])
        return img

    def close(self):
        self.stream_reader.stdin.close()
        self.stream_reader.wait()


class Writer:

    def __init__(self, outscale, audio, height, width, video_save_path, fps):
        out_width, out_height = int(width * outscale), int(height * outscale)
        if out_height > 2160:
            print('You are generating video that is larger than 4K, which will be very slow due to IO speed.',
                  'We highly recommend to decrease the outscale(aka, -s).')

        if audio is not None:
            self.stream_writer = (
                ffmpeg.input('pipe:', format='rawvideo', pix_fmt='bgr24', s=f'{out_width}x{out_height}',
                             framerate=fps).output(
                                 audio,
                                 video_save_path,
                                 pix_fmt='yuv420p',
                                 vcodec='libx264',
                                 loglevel='error',
                                 acodec='copy').overwrite_output().run_async(
                                     pipe_stdin=True, pipe_stdout=True, cmd="ffmpeg"))
        else:
            self.stream_writer = (
                ffmpeg.input('pipe:', format='rawvideo', pix_fmt='bgr24', s=f'{out_width}x{out_height}',
                             framerate=fps).output(
                                 video_save_path, pix_fmt='yuv420p', vcodec='libx264',
                                 loglevel='error').overwrite_output().run_async(
                                     pipe_stdin=True, pipe_stdout=True, cmd="ffmpeg"))

    def write_frame(self, frame):
        frame = frame.astype(np.uint8).tobytes()
        self.stream_writer.stdin.write(frame)

    def close(self):
        self.stream_writer.stdin.close()
        self.stream_writer.wait()


def upscale_image(input_jpg_path, model_name="RealESRGAN_x4plus", outscale=4, suffix=""):
    output_jpg_path = os.path.splitext(input_jpg_path)[0] + f'-upscaled{outscale}x{suffix}.jpg'
    if "-upscaled" in input_jpg_path or os.path.exists(output_jpg_path):
        return None

    upsampler = RealESRGANer(model_name=model_name)

    img = cv2.imread(input_jpg_path, cv2.IMREAD_UNCHANGED)

    try:
        output, _ = upsampler.enhance(img, outscale=outscale)
    except RuntimeError as error:
        print('Error', error)
        print('If you encounter CUDA out of memory, try to set "tile" with a smaller number.')
    else:
        cv2.imwrite(output_jpg_path, output)
    return output_jpg_path


def upscale_video(input_mp4_path, model_name="RealESRGAN_x4plus", outscale=4, suffix=""):
    video_save_path = os.path.splitext(input_mp4_path)[0] + f'-upscaled{outscale}x{suffix}.mp4'
    if "-upscaled" in input_mp4_path or os.path.exists(video_save_path):
        return None

    upsampler = RealESRGANer(model_name=model_name)

    reader = Reader(input_mp4_path)
    audio = reader.get_audio()
    height, width = reader.get_resolution()
    fps = reader.input_fps()
    writer = Writer(outscale, audio, height, width, video_save_path, fps)

    pbar = tqdm(total=len(reader), unit='frame', desc='inference')
    while True:
        img = reader.get_frame()
        if img is None:
            break

        try:
            output, _ = upsampler.enhance(img, outscale=outscale)
        except RuntimeError as error:
            print('Error', error)
            print('If you encounter CUDA out of memory, try to set --tile with a smaller number.')
        else:
            writer.write_frame(output)

        torch.cuda.synchronize()
        pbar.update(1)

    reader.close()
    writer.close()
    return video_save_path
