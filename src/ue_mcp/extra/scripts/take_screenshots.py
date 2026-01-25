"""
Capture screenshots from multiple camera angles around a target point.

Creates temporary CameraActors at specified positions, takes screenshots,
then cleans up the cameras.

Parameters:
    cameras: List of camera specs in format "name@x,y,z" (optional)
    target: Target point as "x,y,z" (default: "0,0,0")
    resolution: Screenshot resolution as "WIDTHxHEIGHT" (default: "1280x720")
    out_dir: Output directory for screenshots (optional)

Usage (CLI):
    python take_screenshots.py
    python take_screenshots.py --cameras front@500,0,500 back@-500,0,500
    python take_screenshots.py --target 100,0,50 --resolution 1920x1080
    python take_screenshots.py --out-dir D:/screenshots

Usage (MCP):
    editor_level_screenshot(cameras=["front@500,0,500", "back@-500,0,500"])
"""

import argparse
import json
import os
import unreal

# 存储创建的 camera actors，以便后续删除
created_cameras = []

# 截图结果
screenshot_results = []

# 默认摄像机配置
DEFAULT_CAMERA = ("Camera", unreal.Vector(800, 0, 800))

# 运行时配置（由 parse_args 填充）
config = {
    "target": unreal.Vector(0, 0, 0),
    "camera_configs": [],
    "resolution_width": 1280,
    "resolution_height": 720,
    "out_dir": None,
}


def parse_camera_spec(spec: str) -> tuple:
    """
    解析摄像机规格字符串。
    格式: name@x,y,z
    例如: front@500,0,500
    返回: (name, unreal.Vector)
    """
    if "@" not in spec:
        raise ValueError(f"Invalid camera spec '{spec}', expected format: name@x,y,z")

    name, coords = spec.split("@", 1)
    parts = coords.split(",")
    if len(parts) != 3:
        raise ValueError(f"Invalid coordinates in '{spec}', expected x,y,z")

    x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
    return (name, unreal.Vector(x, y, z))


def parse_vector(spec: str) -> unreal.Vector:
    """
    解析坐标字符串。
    格式: x,y,z
    例如: 100,0,50
    返回: unreal.Vector
    """
    parts = spec.split(",")
    if len(parts) != 3:
        raise ValueError(f"Invalid coordinates '{spec}', expected x,y,z")

    x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
    return unreal.Vector(x, y, z)


def parse_resolution(spec: str) -> tuple:
    """
    解析分辨率字符串。
    格式: widthxheight
    例如: 1920x1080
    返回: (width, height)
    """
    parts = spec.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"Invalid resolution '{spec}', expected WIDTHxHEIGHT")

    width, height = int(parts[0]), int(parts[1])
    return (width, height)


def parse_args():
    """解析命令行参数并生成 camera 配置"""
    # Bootstrap from environment variables for MCP mode
    from ue_mcp_capture.utils import bootstrap_from_env
    bootstrap_from_env()

    parser = argparse.ArgumentParser(
        description="Capture multi-angle screenshots",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # 摄像机配置
    parser.add_argument(
        "--cameras",
        type=str,
        nargs="*",
        help="Camera positions: name@x,y,z (e.g., front@500,0,500 back@-500,0,500)"
    )

    # 目标点
    parser.add_argument(
        "--target",
        type=str,
        default="0,0,0",
        help="Target point: x,y,z (default: 0,0,0)"
    )

    # 截图分辨率
    parser.add_argument(
        "--resolution",
        type=str,
        default="1280x720",
        help="Screenshot resolution: WIDTHxHEIGHT (default: 1280x720)"
    )

    # 输出目录
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory for screenshots (default: project's Saved/Screenshots)"
    )

    args = parser.parse_args()

    # 解析目标点
    try:
        config["target"] = parse_vector(args.target)
    except ValueError as e:
        print(f"Error parsing target: {e}")
        config["target"] = unreal.Vector(0, 0, 0)

    # 解析分辨率
    try:
        width, height = parse_resolution(args.resolution)
        config["resolution_width"] = width
        config["resolution_height"] = height
    except ValueError as e:
        print(f"Error parsing resolution: {e}, using default 1280x720")
        config["resolution_width"] = 1280
        config["resolution_height"] = 720

    # 设置输出目录
    if args.out_dir:
        config["out_dir"] = args.out_dir
        # 确保目录存在
        os.makedirs(args.out_dir, exist_ok=True)
        print(f"Output directory: {args.out_dir}")

    # 生成 camera 配置
    camera_configs = []

    if args.cameras:
        for spec in args.cameras:
            try:
                name, position = parse_camera_spec(spec)
                camera_configs.append((name, position))
                print(f"Camera '{name}' at {position}")
            except ValueError as e:
                print(f"Warning: {e}, skipping")
    else:
        # 使用默认摄像机
        camera_configs.append(DEFAULT_CAMERA)
        print(f"Using default camera at {DEFAULT_CAMERA[1]}")

    config["camera_configs"] = camera_configs

    print(f"Target: {config['target']}")
    print(f"Resolution: {config['resolution_width']}x{config['resolution_height']}")
    print(f"Total cameras: {len(camera_configs)}")

    return args


if __name__ == "__main__":
    parse_args()

    @unreal.AutomationScheduler.add_latent_command
    def create_cameras():
        """创建 CameraActor"""
        global created_cameras
        created_cameras = []

        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        target = config["target"]

        for name, position in config["camera_configs"]:
            camera = actor_subsystem.spawn_actor_from_class(
                unreal.CameraActor,
                position,
                unreal.Rotator(0, 0, 0)
            )

            camera.set_actor_label(name)

            look_rotation = unreal.MathLibrary.find_look_at_rotation(position, target)
            camera.set_actor_rotation(look_rotation, False)

            created_cameras.append(camera)
            print(f"Created camera: {name} at {position}")

        print(f"Total cameras created: {len(created_cameras)}")


    @unreal.AutomationScheduler.add_latent_command
    def take_all_cam_screenshots():
        """对所有 camera 拍摄截图"""
        global created_cameras, screenshot_results
        screenshot_results = []

        width = config["resolution_width"]
        height = config["resolution_height"]
        out_dir = config["out_dir"]

        for cam in created_cameras:
            camera_name = cam.get_actor_label()

            # 构建输出文件名
            if out_dir:
                filename = os.path.join(out_dir, camera_name)
            else:
                filename = camera_name

            task = unreal.AutomationLibrary.take_high_res_screenshot(
                width, height, filename, camera=cam
            )
            if not task.is_valid_task():
                print(f"Failed to create screenshot task for {camera_name}")
                screenshot_results.append({
                    "camera": camera_name,
                    "success": False,
                    "error": "Failed to create task"
                })
                continue

            print(f"Requested screenshot for {camera_name}")
            while not task.is_task_done():
                yield

            screenshot_results.append({
                "camera": camera_name,
                "success": True,
                "filename": filename
            })


    @unreal.AutomationScheduler.add_latent_command
    def cleanup_cameras():
        """删除创建的 camera actors 并输出结果"""
        global created_cameras, screenshot_results

        for cam in created_cameras:
            if unreal.SystemLibrary.is_valid(cam):
                camera_name = cam.get_actor_label()
                cam.destroy_actor()
                print(f"Deleted camera: {camera_name}")

        created_cameras = []
        print("All cameras cleaned up")

        # 输出 JSON 结果
        result = {
            "success": all(r.get("success", False) for r in screenshot_results),
            "screenshot_count": len([r for r in screenshot_results if r.get("success")]),
            "screenshots": screenshot_results,
            "output_dir": config["out_dir"],
            "resolution": f"{config['resolution_width']}x{config['resolution_height']}",
        }
        print(json.dumps(result))
