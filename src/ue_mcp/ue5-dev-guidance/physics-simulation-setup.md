UE5 物理模拟设置指南
=====================

为 Actor 启用物理模拟时，需要注意以下关键设置：


1. Mobility 必须设置为 Movable
-----------------------------
这是最常被遗漏的设置！

StaticMeshComponent 默认的 Mobility 是 Static，在此状态下：
- 物理模拟不会生效
- 对象被视为静态几何体，永远不会移动
- 即使调用 set_simulate_physics(True) 也无效

Python 设置方法：
    mesh_comp.set_mobility(unreal.ComponentMobility.MOVABLE)

必须在调用 set_simulate_physics(True) 之前设置！


2. 启用物理模拟
---------------
Python 设置方法：
    mesh_comp.set_simulate_physics(True)


3. 设置正确的碰撞
-----------------
物理对象需要正确的碰撞设置才能与其他对象交互。

Python 设置方法：
    mesh_comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)

碰撞类型说明：
- NO_COLLISION: 无碰撞
- QUERY_ONLY: 仅查询（射线检测等），无物理碰撞
- PHYSICS_ONLY: 仅物理碰撞，不响应查询
- QUERY_AND_PHYSICS: 同时支持查询和物理碰撞（推荐）


4. 确保有碰撞网格
-----------------
StaticMesh 必须有有效的碰撞网格，否则物理模拟时会穿透其他对象。

引擎自带的基础形状（/Engine/BasicShapes/）已经包含简单碰撞：
- /Engine/BasicShapes/Cube
- /Engine/BasicShapes/Sphere
- /Engine/BasicShapes/Cylinder
- /Engine/BasicShapes/Cone
- /Engine/BasicShapes/Plane

自定义网格需要在导入时生成碰撞，或在编辑器中手动添加。


5. 质量设置（可选）
-------------------
默认情况下，物理引擎会根据网格体积自动计算质量。
如需自定义：

Python 设置方法：
    mesh_comp.set_mass_in_kg(10.0)  # 设置质量为 10 kg


完整示例代码
------------
```python
import unreal

# 创建 StaticMeshActor
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actor = actor_subsystem.spawn_actor_from_class(
    unreal.StaticMeshActor,
    unreal.Vector(0, 0, 500),
    unreal.Rotator(0, 0, 0)
)

# 获取 mesh 组件
mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)

# 设置网格
sphere_mesh = unreal.load_asset("/Engine/BasicShapes/Sphere")
mesh_comp.set_static_mesh(sphere_mesh)

# 关键步骤：按顺序设置物理属性
mesh_comp.set_mobility(unreal.ComponentMobility.MOVABLE)  # 1. 先设置为可移动
mesh_comp.set_simulate_physics(True)                       # 2. 启用物理模拟
mesh_comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)  # 3. 设置碰撞
```


常见问题排查
------------
Q: 物体不下落？
A: 检查 Mobility 是否为 Movable

Q: 物体穿透地面？
A: 检查地面是否有碰撞，物体碰撞是否启用

Q: 物体下落太快/太慢？
A: 检查世界设置中的重力值，或调整物体质量

Q: 物体卡在空中不动？
A: 确认 simulate_physics 已启用，且 Mobility 为 Movable
