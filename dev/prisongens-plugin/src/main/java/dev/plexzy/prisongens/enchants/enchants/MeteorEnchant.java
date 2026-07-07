package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.*;

public class MeteorEnchant extends CustomEnchant {

    public MeteorEnchant() {
        super("meteor", "§6☄ Meteorito", 4,
                75_000, 37_500, EnchantRarity.LEGENDARY,
                "Hace llover meteoritos que impactan en zonas aleatorias de la mina.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int impactos = level + 1; // Nivel 1 → 2 impactos, Nivel 4 → 5 impactos
        List<Block> affected = new ArrayList<>();
        Random rand = new Random();

        for (int i = 0; i < impactos; i++) {
            int dx = rand.nextInt(9) - 4;
            int dz = rand.nextInt(9) - 4;
            Block impact = block.getRelative(dx, 0, dz);

            // Impacto en 2x2 área
            for (int ix = -1; ix <= 1; ix++) {
                for (int iz = -1; iz <= 1; iz++) {
                    Block b = impact.getRelative(ix, 0, iz);
                    if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                        affected.add(b);
                        breakBlock(player, b);
                    }
                }
            }

            Location iLoc = impact.getLocation().add(0.5, 0.5, 0.5);
            player.getWorld().spawnParticle(Particle.LAVA, iLoc, 20, 1, 1, 1);
            player.getWorld().spawnParticle(Particle.EXPLOSION_LARGE, iLoc, 2);
            player.getWorld().playSound(iLoc, Sound.ENTITY_GENERIC_EXPLODE, 0.5f, 1.8f);
        }

        return affected;
    }
}
