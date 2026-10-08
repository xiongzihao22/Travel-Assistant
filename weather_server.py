from mcp.server.fastmcp import FastMCP

from travel_assistant.weather import query_weather

mcp = FastMCP("TravelWeather")
mcp.tool()(query_weather)

if __name__ == "__main__":
    mcp.run(transport="stdio")
