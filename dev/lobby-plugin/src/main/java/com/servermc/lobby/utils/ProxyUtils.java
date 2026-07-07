package com.servermc.lobby.utils;

import com.google.common.io.ByteArrayDataOutput;
import com.google.common.io.ByteStreams;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;

/**
 * Proxy Utilities - Handles BungeeCord/NullCordX plugin messaging.
 * Used to send players to other servers in the network.
 */
public class ProxyUtils {

    /**
     * Send a player to another server via BungeeCord plugin messaging channel.
     * Works with BungeeCord, NullCordX, Waterfall, etc.
     * 
     * @param plugin The plugin instance
     * @param player The player to send
     * @param serverName The target server name (as configured in proxy config)
     */
    public static void sendToServer(Plugin plugin, Player player, String serverName) {
        ByteArrayDataOutput out = ByteStreams.newDataOutput();
        out.writeUTF("Connect");
        out.writeUTF(serverName);
        player.sendPluginMessage(plugin, "BungeeCord", out.toByteArray());
    }

    /**
     * Request the player count of a specific server.
     * The response will arrive via plugin message listener.
     */
    public static void requestPlayerCount(Plugin plugin, Player player, String serverName) {
        ByteArrayDataOutput out = ByteStreams.newDataOutput();
        out.writeUTF("PlayerCount");
        out.writeUTF(serverName);
        player.sendPluginMessage(plugin, "BungeeCord", out.toByteArray());
    }
}
