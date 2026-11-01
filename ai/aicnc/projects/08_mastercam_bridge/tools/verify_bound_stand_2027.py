"""Verify two fresh-process native runs and P01 comparisons; emit a Markdown audit."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'projects/08_mastercam_bridge/src'))
from mastercam_bridge import plan_simulation as p


def verify(root, first, second, output):
    binding = p.validate_bound_stand_2027(root)
    generated = p.load(root / 'generated-native.json')
    native = [p.load(root / f'{label}-native.json') for label in (first, second)]
    sims = [p.load(root / f'{label}-export.json') for label in (first, second)]
    model_hash = p.digest(root / 'stand-2setup.mcam')
    p.require(generated['ok'] and generated['mode'] == 'create', 'Fresh generation evidence missing')
    p.require(len({generated['pid'], *(n['pid'] for n in native)}) == 3, 'Two fresh-process reopens required')
    for n, sim, label in zip(native, sims, (first, second)):
        p.require(n['ok'] and n['mode'] == 'reopen' and n['pid'] == sim['pid'], 'Reopen identity mismatch')
        for key in ('operations', 'stock_size_mm', 'source_sha256', 'plan_sha256', 'model_sha256'):
            p.require(n[key] == generated[key], 'Reopen native data changed: ' + key)
        p.require(n['model_sha256'] == model_hash, 'Saved project changed')
        p.schema(sim, 'simulator_receipt')
        p.validate_bound_stand_simulation(sim)
        p.require(sim['target_sha256'] == binding['target_sha256'], 'Simulation target mismatch')
        helper = p.load(root / f'{label}-helper.json')
        p.require(sim['bridge_sha256'] == helper['sha256'] == p.digest(Path(helper['path'])), 'Simulator binary binding changed')
    for key in ('motion', 'operation_stream', 'checks', 'collision_options', 'quality_policy', 'stock_to_world', 'report_groups'):
        p.require(sims[0][key] == sims[1][key], 'Simulation readback changed: ' + key)
    for key, value in sims[0]['verifiers'][0].items():
        if key != 'ipw_path':
            p.require(value == sims[1]['verifiers'][0][key], 'Verifier readback changed: ' + key)
    ipw_hash = p.digest(root / f'{first}-ipw.stl')
    p.require(ipw_hash == p.digest(root / f'{second}-ipw.stl'), 'Cold reopen IPW changed')
    material = p.load(root / f'{first}-material.json')
    difference = p.load(root / 'cold-reopen-difference.json')
    p.require(material['target']['sha256'] == binding['target_sha256'] and material['ipw']['sha256'] == ipw_hash, 'Material comparison binding changed')
    p.require(difference['target']['sha256'] == difference['ipw']['sha256'] == ipw_hash, 'Reopen comparison binding changed')
    p.require(difference['volumes']['missing_material_mm3'] == difference['volumes']['extra_material_mm3'] == 0, 'Reopen material mismatch')
    v = sims[-1]['verifiers'][0]
    text = f'''# 原生执行与保存重开核验

本件有界软件试验通过。原生创建进程 {generated['pid']}，两个独立重开进程 {native[0]['pid']}、{native[1]['pid']}。

- 2 个加工方向、9 道原生工序、4 个刀具编号，233 条运动完整结束。
- 生成、保存与两次冷重开后，工序参数、刀路范围、循环时间、毛坯尺寸与工程 SHA256 一致。
- 仿真分辨率 {v['precision_mm']} mm；切削容差 {v['cutting_tolerance_mm']} mm；碰撞和刀柄容差 {v['collision_tolerance_mm']} mm。
- 刀柄、刀杆、刀肩对毛坯碰撞检查及运动间检查开启；事件组为零。
- 相对独立 STEP 目标网格，±0.02 mm 阈值的原生过切、残料报告均为空。
- P01 独立闭合网格差集：缺料 {material['volumes']['missing_material_mm3']:.9f} mm³；余料 {material['volumes']['extra_material_mm3']:.9f} mm³。
- 两次冷重开 IPW 文件字节相同，P01 双向材料差集均为 0 mm³；仿真参数及原生结果回读完全一致。

工程 SHA256：`{model_hash}`

最终 IPW SHA256：`{ipw_hash}`

STEP SHA256：`{binding['source_sha256']}`

目标网格 SHA256：`{binding['target_sha256']}`

工艺单 SHA256：`{binding['plan_sha256']}`

这是对本件、虚拟刀具组件及预制毛坯的软件验证。未进行实物夹具/整机碰撞验证、图纸尺寸验收、材料切削参数认证或生产后处理；未在本次 2027 实件上进行原生碰撞/过切故障注入。网格差集不等于精确 STEP 尺寸公差合格。`production_released=false`。
'''
    with output.open('x', encoding='utf-8') as handle:
        handle.write(text)
    print('PASS: ' + str(output))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--first', default='cold1')
    parser.add_argument('--second', default='cold2')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.root, args.first, args.second, args.output)
