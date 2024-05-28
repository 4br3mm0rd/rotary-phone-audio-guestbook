#! /usr/bin/env python3

import asyncio
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from signal import pause

import yaml
from gpiozero import Button

from audioInterface import AudioInterface

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioGuestBook:
    """
    Manages the rotary phone audio guest book application.

    This class initializes the application, handles phone hook events, and
    coordinates audio playback and recording based on the phone's hook status.

    Attributes:
        config_path (str): Path to the application configuration file.
        config (dict): Configuration parameters loaded from the YAML file.
        audio_interface (AudioInterface): Interface for audio playback and recording.
    """

    def __init__(self, config_path, loop):
        """
        Initializes the audio guest book application with specified configuration.

        Args:
            config_path (str): Path to the configuration YAML file.
        """
        self.config_path = config_path
        self.config = self.load_config()
        self.audio_interface = AudioInterface(
            alsa_hw_mapping=self.config["alsa_hw_mapping"],
            format=self.config["format"],
            file_type=self.config["file_type"],
            recording_limit=self.config["recording_limit"],
            sample_rate=self.config["sample_rate"],
            channels=self.config["channels"],
            mixer_control_name=self.config["mixer_control_name"],
        )
        self.loop = loop
        self.setup_hook()

    def load_config(self):
        """
        Loads the application configuration from a YAML file.

        Raises:
            FileNotFoundError: If the configuration file does not exist.
        """
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError as e:
            logger.error(f"Configuration file not found: {e}")
            sys.exit(1)

    def setup_hook(self):
        """
        Sets up the phone hook switch with GPIO based on the configuration.
        """
        hook_gpio = self.config["hook_gpio"]
        pull_up = self.config["hook_type"] == "NC"
        self.hook = Button(hook_gpio, pull_up=pull_up)
        self.hook.when_pressed = self.off_hook_sync
        self.hook.when_released = self.on_hook_sync
        logger.info("Hook setup")

    def off_hook_sync(self):
        logger.info("Off hook sync")
        self.loop.call_soon_threadsafe(asyncio.create_task, self.off_hook())

    def on_hook_sync(self):
        logger.info("On hook sync")
        self.loop.call_soon_threadsafe(asyncio.create_task, self.on_hook())

    async def greet_then_beep(self):
        logger.info("Playing voicemail...")
        was_interrupted = await self.audio_interface.play_audio(
            self.config["greeting"],
            self.config["greeting_volume"],
            self.config["greeting_start_delay"],
        )
        if not was_interrupted:
            logger.info("Playing beep...")
            await self.audio_interface.play_audio(
                self.config["beep"],
                self.config["beep_volume"],
                self.config["beep_start_delay"],
            )

    async def start_recording(self):
        output_file = str(
            Path(self.config["recordings_path"]) / f"{datetime.now().isoformat()}.wav"
        )
        await self.audio_interface.start_recording(output_file)
        logger.info("Recording started...")

    async def off_hook(self):
        """
        Handles the off-hook event to start playback and recording.
        """
        logger.info("Phone off hook, ready to begin!")

        playback_task = asyncio.create_task(self.greet_then_beep())
        record_task = asyncio.create_task(self.start_recording())
        await asyncio.gather(playback_task, record_task)

    async def on_hook(self):
        """
        Handles the on-hook event to stop and save the recording.
        """
        logger.info("Phone on hook. Ending call and saving recording.")
        await asyncio.gather(
            asyncio.create_task(self.audio_interface.stop_playback()),
            asyncio.create_task(self.audio_interface.stop_recording()),
        )

    def run(self):
        """
        Starts the main event loop waiting for phone hook events.
        """
        logger.info("System ready. Lift the handset to start.")
        pause()


async def main():
    CONFIG_PATH = Path(__file__).parent / "../config.yaml"
    logger.info(f"Using configuration file: {CONFIG_PATH}")
    loop = asyncio.get_running_loop()
    guest_book = AudioGuestBook(CONFIG_PATH, loop)
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("Exiting...")


if __name__ == "__main__":
    asyncio.run(main())
