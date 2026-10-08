# surplus_paths 附加路径契约（第15.1节 / v9示例）

这是现有 `/api/operation/pv/run` 和 `/api/operation/hybrid/run` 的可选请求字段，不改变 S0–S3 候选、经济比较或主推荐。数值由后端 `storage.py` 计算，前端只读结果。

## 请求

```json
{
  "storage": {
    "capacities_kwh": [0, 5, 10, 20, 50],
    "round_trip_efficiency": 0.90,
    "quote": {
      "cny_per_kwh": 553.94,
      "installation_cny_per_kwh": 489.88,
      "maintenance_cny_per_year": 300,
      "life_years": 10,
      "source": "CNESA Datalink：2025年储能中标价格分析（2小时系统与EPC均价）",
      "source_url": "https://www.esresearch.com.cn/report/info/detail/?id=6645",
      "source_note": "2小时系统均价553.94 + 2小时EPC均价1043.82的差额作为容量线性安装项；仅为示例拆分，非单一采购报价"
    },
    "export": {
      "price_cny_per_kwh": 0.25,
      "connection_cny": 0,
      "source": "华福证券：分布式光伏行业深度（公开市场化余电示例）",
      "source_url": "https://www.ndrc.gov.cn/xwdt/tzgg/202502/t20250209_1396067.html",
      "reference_url": "https://pdf.dfcfw.com/pdf/H3_AP202406141636236987_1.pdf",
      "policy_source": "国家发展改革委：关于深化新能源上网电价市场化改革的通知",
      "source_note": "公开行业案例以0.25元/kWh作市场化余电示例；政策要求市场化结算，不代表广东固定上网价；小档并网投入按0元粗算。"
    }
  }
}
```

`quote.cny_per_kwh`、`quote.maintenance_cny_per_year`、`quote.life_years` 必须提供；安装费用二选一：旧兼容字段 `installation_cny` 表示一次性固定安装费，或新增 `installation_cny_per_kwh` 表示按容量线性计费。非零容量缺任一必要字段时，该容量的 `economics_status` 为 `incomplete`，不把缺报价当作零元。容量 0 代表不安装，不承担储能固定费用。`export.price_cny_per_kwh` 缺失时保留余电物理量，但卖电金额为 `null`、状态为 `incomplete`；未填写 `connection_cny` 按 0，并显式写入结果。

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
