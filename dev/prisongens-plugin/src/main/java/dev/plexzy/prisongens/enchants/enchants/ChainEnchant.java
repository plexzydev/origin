package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.*;

/**
 * Cadena: Al romper un bloque, la rotura se propaga en cadena
 * a bloques adyacentes del mismo tipo.
 */
public class ChainEnchant extends CustomEnchant {

    public ChainEnchant() {
        super("chain", "§d⛓ Cadena", 5,
                20_000, 10_000, EnchantRarity.RARE,
                "La rotura se propaga en cadena a bloques del mismo tipo.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int maxChain = level * 5 + 5; // Nivel 1→10, Nivel 5→30
        List<Block> affected = new ArrayList<>();
        Set<Block> visited   = new HashSet<>();
        Queue<Block> queue   = new LinkedList<>();

        Material type = block.getType();
        queue.add(block);
        visited.add(block);

        while (!queue.isEmpty() && affected.size() < maxChain) {
            Block current = queue.poll();
            affected.add(current);
            breakBlock(player, current);

            // Partícula de cadena
            Location loc = current.getLocation().add(0.5, 0.5, 0.5);
            player.getWorld().spawnParticle(Particle.SPELL_WITCH, loc, 3, 0.2, 0.2, 0.2);

            // Propagar a vecinos del mismo tipo
            for (BlockFace face : BlockFace.values()) {
                if (face == BlockFace.SELF) continue;
                Block neighbor = current.getRelative(face);
                if (!visited.contains(neighbor) && neighbor.getType() == type) {
                    visited.add(neighbor);
                    queue.add(neighbor);
                }
            }
        }

        if (!affected.isEmpty()) {
            player.getWorld().playSound(block.getLocation(),
                    Sound.ENTITY_ITEM_PICKUP, 0.5f, 1.8f);
        }

        return affected;
    }
}
