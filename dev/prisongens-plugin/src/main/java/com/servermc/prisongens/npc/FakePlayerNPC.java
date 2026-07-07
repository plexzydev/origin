package com.servermc.prisongens.npc;

import com.mojang.authlib.GameProfile;
import com.mojang.authlib.properties.Property;
import net.minecraft.network.protocol.game.*;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ClientInformation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.craftbukkit.CraftServer;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.craftbukkit.entity.CraftPlayer;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import java.util.UUID;

/**
 * Fake Player NPC for PrisonGens - Shows a real player-looking entity with a skin.
 */
public class FakePlayerNPC {

    private final ServerPlayer nmsPlayer;
    private final int entityId;
    private final JavaPlugin plugin;

    public FakePlayerNPC(Location location, String skinOwnerName, JavaPlugin plugin) {
        this.plugin = plugin;
        MinecraftServer server = ((CraftServer) Bukkit.getServer()).getServer();
        ServerLevel level = ((CraftWorld) location.getWorld()).getHandle();

        GameProfile profile = new GameProfile(UUID.randomUUID(), UUID.randomUUID().toString().substring(0, 8));

        // Fetch skin
        try {
            com.destroystokyo.paper.profile.PlayerProfile bukkitProfile = Bukkit.createProfile(skinOwnerName);
            if (bukkitProfile.complete(true)) {
                for (com.destroystokyo.paper.profile.ProfileProperty prop : bukkitProfile.getProperties()) {
                    profile.getProperties().put(prop.getName(), new Property(prop.getName(), prop.getValue(), prop.getSignature()));
                }
            }
        } catch (Exception e) {
            Bukkit.getLogger().warning("[PrisonGens] Error obteniendo skin de " + skinOwnerName + ": " + e.getMessage());
        }

        this.nmsPlayer = new ServerPlayer(server, level, profile, ClientInformation.createDefault());
        this.entityId = nmsPlayer.getId();

        try {
            java.lang.reflect.Field f = sun.misc.Unsafe.class.getDeclaredField("theUnsafe");
            f.setAccessible(true);
            sun.misc.Unsafe unsafe = (sun.misc.Unsafe) f.get(null);
            this.nmsPlayer.connection = (ServerGamePacketListenerImpl) unsafe.allocateInstance(ServerGamePacketListenerImpl.class);
        } catch (Exception e) {
            Bukkit.getLogger().warning("[PrisonGens] Error creando conexion falsa: " + e.getMessage());
        }

        nmsPlayer.setPos(location.getX(), location.getY(), location.getZ());
        nmsPlayer.setRot(location.getYaw(), location.getPitch());
        nmsPlayer.setYHeadRot(location.getYaw());
    }

    public int getEntityId() {
        return entityId;
    }

    public void showTo(Player viewer) {
        ServerGamePacketListenerImpl conn = ((CraftPlayer) viewer).getHandle().connection;

        conn.send(new ClientboundPlayerInfoUpdatePacket(
                ClientboundPlayerInfoUpdatePacket.Action.ADD_PLAYER,
                nmsPlayer));

        conn.send(new ClientboundAddEntityPacket(
                nmsPlayer.getId(),
                nmsPlayer.getUUID(),
                nmsPlayer.getX(),
                nmsPlayer.getY(),
                nmsPlayer.getZ(),
                nmsPlayer.getXRot(),
                nmsPlayer.getYRot(),
                nmsPlayer.getType(),
                0,
                nmsPlayer.getDeltaMovement(),
                nmsPlayer.getYHeadRot()
        ));

        conn.send(new ClientboundRotateHeadPacket(nmsPlayer,
                (byte) ((nmsPlayer.getYHeadRot() * 256.0F) / 360.0F)));

        nmsPlayer.getEntityData().set(
                net.minecraft.world.entity.player.Player.DATA_PLAYER_MODE_CUSTOMISATION,
                (byte) 0x7F
        );
        conn.send(new ClientboundSetEntityDataPacket(
                nmsPlayer.getId(),
                nmsPlayer.getEntityData().getNonDefaultValues()
        ));

        // Hide nametag
        Bukkit.getScheduler().runTask(plugin, () -> {
            org.bukkit.scoreboard.Scoreboard board = Bukkit.getScoreboardManager().getMainScoreboard();
            org.bukkit.scoreboard.Team npcTeam = board.getTeam("npc_hidden");
            if (npcTeam == null) {
                npcTeam = board.registerNewTeam("npc_hidden");
                npcTeam.setOption(org.bukkit.scoreboard.Team.Option.NAME_TAG_VISIBILITY, org.bukkit.scoreboard.Team.OptionStatus.NEVER);
            }
            npcTeam.addEntry(nmsPlayer.getGameProfile().getName());
        });

        // Remove from tab after skin loads
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            if (viewer.isOnline()) {
                conn.send(new ClientboundPlayerInfoRemovePacket(
                        java.util.List.of(nmsPlayer.getUUID())));
            }
        }, 20L);
    }

    public void hideFrom(Player viewer) {
        ServerGamePacketListenerImpl conn = ((CraftPlayer) viewer).getHandle().connection;
        conn.send(new ClientboundRemoveEntitiesPacket(nmsPlayer.getId()));
        conn.send(new ClientboundPlayerInfoRemovePacket(
                java.util.List.of(nmsPlayer.getUUID())));
    }

    public void destroy() {
        for (Player p : Bukkit.getOnlinePlayers()) {
            hideFrom(p);
        }
    }

    public UUID getUUID() {
        return nmsPlayer.getUUID();
    }
}
