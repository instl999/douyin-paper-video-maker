"""Stage orchestration shared by the CLI commands: checked storyboard → voice → timeline."""
from __future__ import annotations

from .project import Project
from .schema import Storyboard
from .timeline import Timeline, build_timeline, srt
from .util import write_json, write_text
from .voice import VoiceTrack, build_voice


def prepare(p: Project, *, engine: str | None = None, force_voice: bool = False,
            strict: bool = False) -> tuple[Storyboard, VoiceTrack, Timeline]:
    """Validated storyboard, voice track and timeline; audio/timeline.json and audio/subtitles.srt are written."""
    sb = p.storyboard(check=True, strict=strict)
    track = build_voice(p, sb.voice, engine, force=force_voice)
    timeline = build_timeline(sb, track)
    write_json(p.audio_dir / "timeline.json", timeline.to_json())
    write_text(p.audio_dir / "subtitles.srt", srt(timeline.cues))
    return sb, track, timeline
