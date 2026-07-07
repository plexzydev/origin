package com.servermc.prisongens.listeners;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.npc.FakePlayerNPC;
import io.netty.channel.*;
import net.minecraft.network.protocol.game.ServerboundInteractPacket;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.entity.CraftPlayer;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;

import java.util.Map;
import java.util.UUID;

/**
 * Intercepts UseEntity packets to detect clicks on FakePlayerNPC entities.
 */
public class NPCClickListener implements Listener {

    private final PrisonGens plugin;

    public NPCClickListener(PrisonGens plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        injectPlayer(event.getPlayer());
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        removePlayer(event.getPlayer());
    }

    private void injectPlayer(Player player) {
        ChannelPipeline pipeline = ((CraftPlayer) player).getHandle().connection.connection.channel.pipeline();
        if (pipeline.get("prisongens_npc") != null) return;

        pipeline.addBefore("packet_handler", "prisongens_npc", new ChannelDuplexHandler() {
            @Override
            public void channelRead(ChannelHandlerContext ctx, Object msg) throws Exception {
                if (msg instanceof ServerboundInteractPacket packet) {
                    // Use reflection to get entity ID
                    try {
                        java.lang.reflect.Field f = ServerboundInteractPacket.class.getDeclaredField("entityId");
                        if (!f.canAccess(null)) {
                            // Try alternate field names
                            for (java.lang.reflect.Field field : ServerboundInteractPacket.class.getDeclaredFields()) {
                                if (field.getType() == int.class) {
                                    field.setAccessible(true);
                                    int entityId = field.getInt(packet);
                                    checkNPCClick(player, entityId);
                                    break;
                                }
                            }
                        } else {
                            f.setAccessible(true);
                            int entityId = f.getInt(packet);
                            checkNPCClick(player, entityId);
                        }
                    } catch (Exception e) {
                        // Fallback: try all int fields
                        for (java.lang.reflect.Field field : ServerboundInteractPacket.class.getDeclaredFields()) {
                            if (field.getType() == int.class) {
                                try {
                                    field.setAccessible(true);
                                    int entityId = field.getInt(packet);
                                    checkNPCClick(player, entityId);
                                    break;
                                } catch (Exception ignored) {}
                            }
                        }
                    }
                }
                super.channelRead(ctx, msg);
            }
        });
    }

    private void checkNPCClick(Player player, int entityId) {
        for (Map.Entry<UUID, FakePlayerNPC> entry : plugin.getIslandManager().getAllNPCs().entrySet()) {
            if (entry.getValue().getEntityId() == entityId) {
                UUID islandOwner = entry.getKey();
                // Run on main thread
                Bukkit.getScheduler().runTask(plugin, () -> {
                    // Check if player owns this island
                    var island = plugin.getIslandManager().getIsland(player);
                    if (island != null && island.owner.equals(islandOwner)) {
                        plugin.getGensManager().openGensMenu(player);
                    } else {
                        player.sendMessage("§c§l✖ §7Esta no es tu isla.");
                    }
                });
                break;
            }
        }
    }

    private void removePlayer(Player player) {
        try {
            Channel channel = ((CraftPlayer) player).getHandle().connection.connection.channel;
            channel.eventLoop().submit(() -> {
                channel.pipeline().remove("prisongens_npc");
                return null;
            });
        } catch (Exception ignored) {}
    }
}
