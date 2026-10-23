import { describe, expect, it } from "vitest";

import { csvFilename, tableCsv } from "./export";
import type { TableSpec } from "./table";

const spec = (moe: boolean): TableSpec => ({
  caption: "Median household income · Ward",
  valueLabel: "Median household income",
  countLabel: "Households",
  source: "ACS 2020-2024, B19001",
  rows: [
    { id: "columbus-ward-01", name: "Columbus Ward 01", value: 52000, display: "$52,000 ± $4,000", count: 900, countDisplay: "900", note: "", moe: moe ? 4000 : null },
    { id: "x", name: '=HYPERLINK("evil")', value: null, display: "—", count: null, countDisplay: "—", note: "No estimate, sorry", moe: null },
  ],
});

describe("tableCsv", () => {
  it("writes one statistic per area, with the margin of error only when there is one", () => {
    const lines = tableCsv(spec(true)).trimEnd().split("\r\n");
    expect(lines[0]).toBe("feature_id,area,measure,value,value_formatted,moe_90,count_label,count,notes,view,source_file");
    expect(lines[1]).toBe(`columbus-ward-01,Columbus Ward 01,Median household income,52000,"$52,000 ± $4,000",4000,Households,900,,Median household income · Ward,"ACS 2020-2024, B19001"`);
    expect(lines).toHaveLength(3);
    expect(tableCsv(spec(false)).split("\r\n")[0]).not.toContain("moe_90");
  });

  it("quotes separators and defuses formulas; areas without a value stay blank", () => {
    const row = tableCsv(spec(false)).split("\r\n")[2];
    expect(row).toBe(`x,"'=HYPERLINK(""evil"")",Median household income,,,Households,,"No estimate, sorry",Median household income · Ward,"ACS 2020-2024, B19001"`);
  });

  it("keeps negative numbers as numbers", () => {
    const s = spec(false);
    s.rows = [{ ...s.rows[0]!, display: "-$12,500", value: -12500 }];
    expect(tableCsv(s).split("\r\n")[1]).toContain(`,-12500,"-$12,500",`);
  });

  it("names the file after the view", () => {
    expect(csvFilename(spec(false))).toBe("median-household-income-ward.csv");
  });
});
