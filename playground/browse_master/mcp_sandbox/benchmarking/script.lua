wrk.method = "POST"

wrk.headers["Content-Type"] = "application/json"


wrk.body = [[
{
    "code": "\ndef sum(a, b):\n    return a+b\n\noutput = sum(1,2)\nprint(output)"
}
]]

function response(status, header, body)
    if status ~= 200 then
        print("Status: " .. status)
        print("Body: " .. body)
    end
end