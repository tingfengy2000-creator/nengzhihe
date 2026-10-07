# surplus_paths 附加路径契约（第15.1节）

这是现有 `/api/operation/pv/run` 和 `/api/operation/hybrid/run` 的可选请求字段，不改变 S0–S3 候选、经济比较或主推荐。数值由后端 `storage.py` 计算，前端只读结果。

## 请求

```json
{
  "storage": {
    "capacities_kwh": [0, 5, 10, 20, 50],
    "round_trip_efficiency": 0.90,
    "quote": {
      "cny_per_kwh": 1200,
      "installation_cny": 3000,
      "maintenance_cny_per_year": 120,
      "life_years": 10,
      "source": "示例报价，仅用于演示"
    },
    "export": {
      "price_cny_per_kwh": 0.30,
      "connection_cny": 0,
      "source": "用户情景；待当地电网批复"
    }
  }
}
```

`quote` 任一非零容量字段缺失时，该容量的 `economics_status` 为 `incomplete`；不把缺报价当作零元。容量 0 代表不安装，不承担储能固定费用。`export.price_cny_per_kwh` 缺失时保留余电物理量，但卖电金额为 `null`、状态为 `incomplete`；未填写 `connection_cny` 按 0，并显式写入结果。

## 响应片段

每个 PV/风光候选新增：

```json
{
  "surplus_paths": {
    "surplus_kwh_year1": 123.4,
    "storage": {
      "status": "calculated",
      "candidates": [
        {
          "capacity_kwh": 0,
          "recovered_kwh_year1": 0,
          "initial_investment_cny": 0,
          "annual_bill_saving_cny": 0,
          "study_period_net_benefit_cny": 0,
          "economics_status": "complete"
        }
      ],
      "recommended_capacity_kwh": 0,
      "economics_basis": "年末不折现；按放电所在小时分时购电价节省；不进入四方案推荐"
    },
    "export": {
      "path": {
        "surplus_kwh_year1": 123.4,
        "annual_revenue_cny": 37.02,
        "study_period_revenue_cny": 370.2,
        "economics_status": "complete"
      }
    }
  }
}
```

储能和卖电从同一份无储能物理余电 `generation - self_use` 独立起算，二者不是“存还是卖”的联合优化。允许外送时，储能路径仍计算其理想上限；卖电路径仍单独按全部余电粗算。储能不含电池衰减、温度影响、峰谷套利或优化求解，不是第五种方案或现场投资建议；卖电不代表并网资格或实际结算。
