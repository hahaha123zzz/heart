import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AssessmentEvidence } from "@/features/heart/AssessmentEvidence";
const request=vi.hoisted(()=>vi.fn());
vi.mock("@/shared/api/client",()=>({requestJson:request}));
afterEach(cleanup);beforeEach(()=>request.mockReset());
it("loads one receipt only when opened, marks lag and never invents mastery",async()=>{
 request.mockResolvedValue({publication_status:"pending",catalog_current:true,evidence:null,misconceptions:[]});
 render(<AssessmentEvidence jobId="own-job"/>);expect(request).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"查看同步证据与误区"}));
 expect(await screen.findByText("宿主同步尚未完成，暂不展示为已同步证据。")).toBeInTheDocument();
 expect(request).toHaveBeenCalledWith("/api/heart/learning/evidence/own-job",expect.objectContaining({cache:"no-store"}));
});
it("shows the original quote and receipt time, with old-catalog and misconception qualifiers",async()=>{
 request.mockResolvedValue({publication_status:"published",catalog_current:false,vendor_evidence_id:"vendor-proof",
 evidence:{id:12,source_quote:"真实作答",assessed_mastered:false,synced_at:"2026-11-20T10:00:00Z"},
 misconceptions:[{id:1,type:"因果混淆",status:"hypothesis",reason:"仍需验证"}]});
 render(<AssessmentEvidence jobId="own-job"/>);fireEvent.click(screen.getByRole("button",{name:"查看同步证据与误区"}));
 expect(await screen.findByText("真实作答")).toBeInTheDocument();
 expect(screen.getByText(/旧教材目录/)).toBeInTheDocument();expect(screen.getByText(/待确认线索/)).toBeInTheDocument();
 expect(screen.getByText("该次同步时尚未达到掌握要求")).toBeInTheDocument();
});
it("aborts a late receipt when closed and retries a failed request",async()=>{
 let resolve!:(value:unknown)=>void;request.mockImplementationOnce(()=>new Promise(done=>{resolve=done}));
 render(<AssessmentEvidence jobId="own-job"/>);fireEvent.click(screen.getByRole("button",{name:"查看同步证据与误区"}));
 const signal=request.mock.calls[0][1].signal as AbortSignal;
 fireEvent.click(screen.getByRole("button",{name:"收起同步证据与误区"}));expect(signal.aborted).toBe(true);
 resolve({evidence:{source_quote:"过期内容"}});await waitFor(()=>expect(screen.queryByText("过期内容")).toBeNull());
 request.mockRejectedValueOnce(new Error("offline"));fireEvent.click(screen.getByRole("button",{name:"查看同步证据与误区"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("读取失败");
 request.mockResolvedValue({publication_status:"blocked",catalog_current:true,evidence:null,misconceptions:[]});
 fireEvent.click(screen.getByRole("button",{name:"重新读取同步证据"}));expect(await screen.findByText(/同步受阻/)).toBeInTheDocument();
});
