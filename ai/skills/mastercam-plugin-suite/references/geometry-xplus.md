# MP、X+ 与几何工具

先用 `mc_catalog` 查 `typed.<action>`，再读 `mc_capability` 的合同。以下是独立重建模块或 API29 适配器的参数接口；原版 X+ DLL 的 FT 入口仍是交互界面，不是隐藏的无头 API。

| 原菜单/用途 | 直接 action | 决策要点 |
|---|---|---|
| MP 边线/二维边线 | mp.edges | 单个可见实体、闭合平面面、直线边；3D 或世界 XY 投影。已有可见输出层，不做隐藏线消除。 |
| MP 曲面法向 | mp.reverse_normals | 只接受独立可见曲面 ID，逐面反转；实体面不适用。 |
| MP 曲面类型 | mp.select_surface_types | `types` 使用 mc_inspect 返回的完整类型名称，例如 Mastercam.Surfaces.NURBSSurface；从所有可见独立曲面中追加选择。 |
| MP 半径 | mp.select_radius | `solid_ids` 明确范围；半径是当前文档单位的闭区间，不是直径；返回面 PID，但选择整个实体。 |
| SVGImage | xplus.svg | XML 内容，明确缩放、偏移、FlipY、公差、层和颜色；只解析支持的 SVG 几何，不读取外部资源。 |
| TpSketcher | xplus.sketch | ViewID + 平面局部 XY 链，depth 为局部 Z；非零平面原点参与世界转换。machining 与 existing_tool_slot 同时为 null 时只建线，否则创建真实轮廓工序。 |
| MergeFixture / FixtureSetup | xplus.fixture_copy | 明确原点 reference、目标 target、附加平移和世界 Z 的 90° 倍数；复制点、曲线、实体；不读取 .smk 专有库。 |
| Hirth | xplus.fit_plane | 两个轴方向与角度网格、候选上限、匹配容差；拟合不是机床运动学或碰撞验证。 |
| SetupSheet / ToolList | xplus.setup_sheet | 明确 selected/all 范围，输出 HTML/XLSX/CSV；不可用字段保留原因。 |
| ElectrodesReport | xplus.electrode_report | 明确选区、参考 ViewID、每项参考点来源；用户 C 角不是自动推导的机床姿态。 |
| level2stl | xplus.levels_to_stl | 所有可见层内未隐藏对象，世界坐标，公差≤1；校验二进制三角面及范围，不保证网格封闭或每个源对象均参与网格。 |
| XSnapShot | xplus.capture | 输出当前视图白底 PNG，恢复背景和轴；不操作剪贴板。 |
| SwitchBG | xplus.gradient | Off/Horizontal/Vertical/Diagonal；回滚拒绝覆盖后续背景修改。 |
| Holder_CH | xplus.holder_library | 分段上/下直径和段高、明确单位；创建独立 tooldb，关闭重开回读，不改用户现有库。 |
| ChainIt（已有工序链） | xplus.select_operation_chains | 从明确工序的完整链取得几何 ID 并追加选择；任意几何的交互链拾取用 chain_picker 面板。 |
| SetWorkoffset | xplus.work_offset | 修改已有 ViewID 的 WorkOffsetNumber；检查预览中受影响的工序，不把编号当空间偏移。 |
| RenameNCI | xplus.rename_nci | 按实际工序 ID 设置无扩展名的 ASCII 程序名；保留目录，恢复工序选择，不运行后处理或改磁盘文件名。 |
| 几何工具 | geometry.copy_edit | 原对象保留，只在独立副本上居中、旋转、构图平面对齐、平面着色、标注、合并或分层。合并至少两段相连曲线；不接受任意实体倒角。 |

全部 action 使用 `mc_prepare_change → mc_apply_plan → mc_rollback_plan`。预览期间的临时选择在同次宿主调用内恢复；选择 action 的 apply 才保留新的选择。不要并发操作宿主。

几何/刀具/平面的回滚只处理该计划记录的对象，并检查后续变化。法向与 NCI 恢复原值，不承诺恢复数据库时间戳或旧刀路缓存。导出的报告、STL、截图在 rollback 后保留；刀柄回滚删除该新增刀柄，保留新库文件。需要交付时从结果中的实际路径取文件，不能猜路径。

`xplus.sketch` 的加工模式由明确的 `Regenerate` 控制是否算刀路；几何创建、工序建立和重算是不同结果。新建期间产生的附加平面也纳入记录；回滚只删除指纹未变且没有引用的自有平面。已有平底刀槽必须匹配直径；实际 CutParams 工序类型设为 Basic，结束创建事务后才计算刀路，并回读原生返回值与新包装对象的 Dirty。当前接口不自动推断材料、刀号或切削参数。

## 仍需界面的流程

`mc_open_panel` 提供八个固定入口：advanced_drilling、tapping、solid_boundary、chain_picker、bee_hub、geometry_native、middle_confirm、geometry_editor。调用前核对 expected_document，使用新的 request_id；调用后须用界面工具观察实际面板，再执行用户授权的操作并读取实际结果。

返回 `status=queued, business_completed=false` 只表示已排队。它不证明窗口已打开，更不证明加工成功。当前会话没有界面工具时，保留这个限制；不得把排队回执包装成完整自动执行。未关闭的工作流期间不再排队或发送原生编辑请求；适配层同时检查已打开的受限插件窗体。面板调度使用宿主 UI 定时器执行 RunFT，回执另附 panel_receipt 记录调度状态。CIMCO 不在这些入口中。

## 失败与边界

超时先查 `mc_request_status`，不重发。prepare 失败不会产生可执行计划；apply 失败保存审计，但不保证所有外部文件都不存在。读取实际 `status`、返回对象和逐项回读。出现回滚冲突时保留 ID 和审计，禁止全局 Undo 或删除来源对象。

实体复制使用已验证且固定构建的独立内核副本。量测只对自有临时副本创建角点，随后删除，核对源实体时间戳和全库清单。原生构建与依赖哈希不符时停止并报告。几何校验涵盖公开属性、时间戳、端点/边界、面身份和记录的参数；不是完整 B-rep 或任意下游引用的证明。测试范围以 `ai/validation/geometry-native-acceptance.json` 为准。
