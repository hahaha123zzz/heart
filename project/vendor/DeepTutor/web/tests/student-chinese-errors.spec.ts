import {expect,it} from "vitest";
import {ApiError,translateApiMessage} from "@/shared/api/errors";
it("shows Chinese errors while preserving original machine-readable details",()=>{
 const raw={code:"network_error",message:"Unable to reach the server",retryable:true,scope:"network" as const};
 const error=new ApiError(raw);expect(error.message).toBe("无法连接服务器，请检查网络后重试。");expect(error.appError).toEqual(raw);
 expect(translateApiMessage("404 Not Found")).toBe("404 未找到请求的内容。");
 expect(translateApiMessage("HTTP_PROVIDER_X_103")).toBe("HTTP_PROVIDER_X_103");
});
