import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import StudentAccountSettings from "@/features/heart/StudentAccountSettings";
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
it("persists only supported display fields and requires readback after an uncertain save",async()=>{
 const fetcher=vi.fn(async(input:unknown,options?:RequestInit)=>{if(options?.method==="PUT")throw new Error("lost");return {ok:true,json:async()=>String(input).includes("/profile")?{username:"student-a"}:{language:"zh",response_language:"zh",code_block_wrap_long_lines:true}}});vi.stubGlobal("fetch",fetcher);
 render(<StudentAccountSettings/>);const button=screen.getByRole("button",{name:"保存显示设置"});expect(button).toBeDisabled();await waitFor(()=>expect(button).toBeEnabled());expect(screen.getByText(/student-a/)).toBeVisible();expect(screen.getByText("界面语言：简体中文")).toBeVisible();fireEvent.click(button);await screen.findByText("未能确认保存结果，请重新读取后核对。");expect(button).toBeDisabled();const write=fetcher.mock.calls.find(([,o])=>o?.method==="PUT");expect(JSON.parse(String(write?.[1]?.body))).toEqual({language:"zh",response_language:"zh",code_block_wrap_long_lines:true});expect(screen.getByRole("link",{name:"管理教学偏好"})).toHaveAttribute("href","/memory");
});
