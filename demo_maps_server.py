from mcp.server.fastmcp import FastMCP

mcp = FastMCP("DemoMaps")


@mcp.tool()
def demo_route() -> dict:
    """返回固定的北京行程样例，仅用于离线演示，不能用于实际导航。"""
    return {
        "demo": True,
        "source": "固定演示样例，未查询高德或实时路况",
        "itinerary": ["上午：天坛公园", "下午：前门与大栅栏", "傍晚：南锣鼓巷"],
        "notice": "此样例不含交通距离、用时及营业信息；真实路线请启用 live 模式。",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
